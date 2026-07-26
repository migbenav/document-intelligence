import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatBytes } from '@/lib/utils';
import type { DocumentCard } from '@/types/documentCard';

export interface DocumentCardViewProps {
  card: DocumentCard;
  onRetry?: () => void;
}

const CLASSIFICATION_LABELS: Record<string, string> = {
  normative: 'Normativo',
  guide: 'Guía',
  manual: 'Manual',
  procedure: 'Procedimiento',
  technical: 'Técnico',
  narrative: 'Narrativo',
  other: 'Otro',
};

const ORGANIZATION_LABELS: Record<string, string> = {
  numbered_articles: 'Artículos numerados',
  headed_sections: 'Secciones con encabezados',
  hierarchical_numbering: 'Numeración jerárquica',
  free_form: 'Formato libre',
};

/**
 * Displays a completed or partial Document Card.
 *
 * - Completed: shows title, summary, classification badge, organization type, statistics, file metadata.
 * - Partial: shows all local fields and a retry button where summary/classification would be.
 * - Outdated: displays a warning indicator when the document has changed since analysis.
 */
export function DocumentCardView({ card, onRetry }: DocumentCardViewProps) {
  const isPartial = card.status === 'partial' || card.status === 'failed_llm';

  return (
    <Card data-testid="document-card-view">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-xl">{card.title}</CardTitle>
          {card.outdated && (
            <Badge
              variant="destructive"
              role="status"
              aria-label="Documento desactualizado"
            >
              Desactualizado
            </Badge>
          )}
        </div>

        {/* Classification badge — only for completed cards */}
        {card.classification && (
          <Badge variant="secondary" aria-label={`Clasificación: ${CLASSIFICATION_LABELS[card.classification] ?? card.classification}`}>
            {CLASSIFICATION_LABELS[card.classification] ?? card.classification}
          </Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Summary and classification area */}
        {isPartial ? (
          <div className="flex items-center">
            <Button
              variant="outline"
              onClick={onRetry}
              aria-label="Reintentar análisis con IA"
            >
              Reintentar análisis
            </Button>
          </div>
        ) : (
          card.summary && (
            <p className="text-sm text-muted-foreground">{card.summary}</p>
          )
        )}

        {/* Organization type */}
        <div className="text-sm">
          <span className="font-medium">Organización: </span>
          <span>{ORGANIZATION_LABELS[card.organization_type] ?? card.organization_type}</span>
        </div>

        {/* Statistics grid */}
        <div
          className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm"
          aria-label="Estadísticas del documento"
        >
          <div>
            <span className="text-muted-foreground">Bloques: </span>
            <span className="font-medium">{card.statistics.total_chunks}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Secciones: </span>
            <span className="font-medium">{card.statistics.sections_detected}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Niveles: </span>
            <span className="font-medium">{card.statistics.hierarchy_levels}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Índice: </span>
            <span className="font-medium">
              {card.statistics.has_existing_index ? 'Sí' : 'No'}
            </span>
          </div>
        </div>

        {/* File metadata */}
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span>{formatBytes(card.file_metadata.size_bytes)}</span>
          <span className="uppercase">{card.file_metadata.format}</span>
          {card.file_metadata.language && (
            <span className="uppercase">{card.file_metadata.language}</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
