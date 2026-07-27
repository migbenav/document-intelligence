import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { OptionsPanel } from '@/components/analysis/OptionsPanel';
import { TranslationProvider } from '@/i18n';
import { useAnalysisStore } from '@/store/analysisStore';
import type { AnalysisStatusSummary } from '@/types/analysis';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider locale="en">{ui}</TranslationProvider>);
}

const defaultStatuses: AnalysisStatusSummary = {
  build_index: { status: 'not_started', updated_at: null },
  section_relations: { status: 'not_started', updated_at: null },
  questions_answered: { status: 'not_started', updated_at: null },
  conclusions: { status: 'not_started', updated_at: null },
};

describe('OptionsPanel', () => {
  let triggerAnalysisSpy: ReturnType<typeof vi.fn>;
  let fetchStatusesSpy: ReturnType<typeof vi.fn>;
  let fetchResultSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    triggerAnalysisSpy = vi.fn();
    fetchStatusesSpy = vi.fn();
    fetchResultSpy = vi.fn();
    useAnalysisStore.setState({
      statuses: defaultStatuses,
      results: {},
      activeAnalysis: null,
      error: null,
      fetchStatuses: fetchStatusesSpy,
      triggerAnalysis: triggerAnalysisSpy,
      fetchResult: fetchResultSpy,
      reset: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('option filtering by classification', () => {
    it('renders all 4 options for non-narrative classification', () => {
      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      expect(screen.getByTestId('analysis-option-build_index')).toBeInTheDocument();
      expect(screen.getByTestId('analysis-option-section_relations')).toBeInTheDocument();
      expect(screen.getByTestId('analysis-option-questions_answered')).toBeInTheDocument();
      expect(screen.getByTestId('analysis-option-conclusions')).toBeInTheDocument();
    });

    it('renders only 2 options for narrative classification', () => {
      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="narrative" />
      );

      expect(screen.queryByTestId('analysis-option-build_index')).not.toBeInTheDocument();
      expect(screen.queryByTestId('analysis-option-section_relations')).not.toBeInTheDocument();
      expect(screen.getByTestId('analysis-option-questions_answered')).toBeInTheDocument();
      expect(screen.getByTestId('analysis-option-conclusions')).toBeInTheDocument();
    });

    it('renders all 4 options when classification is null (partial card)', () => {
      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification={null} />
      );

      expect(screen.getByTestId('analysis-option-build_index')).toBeInTheDocument();
      expect(screen.getByTestId('analysis-option-section_relations')).toBeInTheDocument();
      expect(screen.getByTestId('analysis-option-questions_answered')).toBeInTheDocument();
      expect(screen.getByTestId('analysis-option-conclusions')).toBeInTheDocument();
    });
  });

  describe('triggering analysis', () => {
    it('calls triggerAnalysis when Analyze button is clicked', () => {
      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      const analyzeButtons = screen.getAllByTestId('analyze-button');
      fireEvent.click(analyzeButtons[0]!);

      expect(triggerAnalysisSpy).toHaveBeenCalledWith('doc-1', 'build_index');
    });

    it('calls triggerAnalysis with correct type for each option', () => {
      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification={null} />
      );

      const analyzeButtons = screen.getAllByTestId('analyze-button');
      // 4 buttons in order: build_index, section_relations, questions_answered, conclusions
      fireEvent.click(analyzeButtons[1]!);
      expect(triggerAnalysisSpy).toHaveBeenCalledWith('doc-1', 'section_relations');

      fireEvent.click(analyzeButtons[2]!);
      expect(triggerAnalysisSpy).toHaveBeenCalledWith('doc-1', 'questions_answered');

      fireEvent.click(analyzeButtons[3]!);
      expect(triggerAnalysisSpy).toHaveBeenCalledWith('doc-1', 'conclusions');
    });
  });

  describe('status indicators', () => {
    it('renders no status badge for not_started status', () => {
      useAnalysisStore.setState({
        statuses: {
          ...defaultStatuses,
          build_index: { status: 'not_started', updated_at: null },
        },
      });

      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      // For not_started, no status badge (In progress, Completed, Outdated, Failed) is shown
      expect(screen.queryByLabelText('In progress...')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Completed')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Outdated')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Failed')).not.toBeInTheDocument();
    });

    it('renders spinner badge for in_progress status', () => {
      useAnalysisStore.setState({
        statuses: {
          ...defaultStatuses,
          build_index: { status: 'in_progress', updated_at: null },
        },
        activeAnalysis: 'build_index',
      });

      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      expect(screen.getByLabelText('In progress...')).toBeInTheDocument();
      expect(screen.getByTestId('analyzing-button')).toBeDisabled();
    });

    it('renders completed badge and View button for completed status', () => {
      useAnalysisStore.setState({
        statuses: {
          ...defaultStatuses,
          build_index: { status: 'completed', updated_at: '2024-01-01T00:00:00Z' },
        },
      });

      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      expect(screen.getByLabelText('Completed')).toBeInTheDocument();
      expect(screen.getByTestId('view-button')).toBeInTheDocument();
    });

    it('renders outdated badge with View and Re-analyze buttons', () => {
      useAnalysisStore.setState({
        statuses: {
          ...defaultStatuses,
          build_index: { status: 'outdated', updated_at: '2024-01-01T00:00:00Z' },
        },
      });

      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      expect(screen.getByLabelText('Outdated')).toBeInTheDocument();
      expect(screen.getByTestId('view-button')).toBeInTheDocument();
      expect(screen.getByTestId('reanalyze-button')).toBeInTheDocument();
    });

    it('renders failed badge with Retry button', () => {
      useAnalysisStore.setState({
        statuses: {
          ...defaultStatuses,
          build_index: { status: 'failed', updated_at: '2024-01-01T00:00:00Z' },
        },
      });

      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      expect(screen.getByLabelText('Failed')).toBeInTheDocument();
      expect(screen.getByTestId('retry-button')).toBeInTheDocument();
    });

    it('clicking Retry triggers analysis again', () => {
      useAnalysisStore.setState({
        statuses: {
          ...defaultStatuses,
          build_index: { status: 'failed', updated_at: '2024-01-01T00:00:00Z' },
        },
      });

      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      fireEvent.click(screen.getByTestId('retry-button'));
      expect(triggerAnalysisSpy).toHaveBeenCalledWith('doc-1', 'build_index');
    });

    it('clicking Re-analyze triggers analysis again', () => {
      useAnalysisStore.setState({
        statuses: {
          ...defaultStatuses,
          build_index: { status: 'outdated', updated_at: '2024-01-01T00:00:00Z' },
        },
      });

      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      fireEvent.click(screen.getByTestId('reanalyze-button'));
      expect(triggerAnalysisSpy).toHaveBeenCalledWith('doc-1', 'build_index');
    });

    it('clicking View calls fetchResult', () => {
      useAnalysisStore.setState({
        statuses: {
          ...defaultStatuses,
          build_index: { status: 'completed', updated_at: '2024-01-01T00:00:00Z' },
        },
      });

      renderWithProviders(
        <OptionsPanel documentId="doc-1" classification="regulatory" />
      );

      fireEvent.click(screen.getByTestId('view-button'));
      expect(fetchResultSpy).toHaveBeenCalledWith('doc-1', 'build_index');
    });
  });

  describe('fetchStatuses on mount', () => {
    it('calls fetchStatuses with documentId on mount', () => {
      renderWithProviders(
        <OptionsPanel documentId="doc-123" classification="regulatory" />
      );

      expect(fetchStatusesSpy).toHaveBeenCalledWith('doc-123');
    });
  });
});
