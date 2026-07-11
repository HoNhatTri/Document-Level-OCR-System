import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Activity, AlertTriangle, Clock3, RefreshCw, Server, Sparkles } from "lucide-react";
import { apiUrl } from "../api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Progress } from "./ui/progress";

interface MonitoringDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface MonitoringSnapshot {
  timestamp: string;
  uptime_seconds: number;
  api: {
    requests_total: number;
    errors_total: number;
    error_rate: number;
    latency_ms: {
      avg: number;
      p50: number;
      p95: number;
      max: number;
    };
    recent: Array<{
      timestamp: string;
      method: string;
      path: string;
      status_code: number;
      latency_ms: number;
      is_error: boolean;
    }>;
  };
  ocr: {
    runs_total: number;
    poor_rate: number;
    average_raw_error_rate: number;
    average_after_ai_error_rate: number;
    average_improvement_rate: number;
    duration_ms: {
      avg: number;
      p95: number;
      max: number;
    };
    latest: null | {
      filename: string;
      document_type: string;
      estimated_raw_error_rate: number;
      estimated_after_ai_error_rate: number;
      estimated_improvement_rate: number;
      quality_level: string;
      llm_status: string;
      layoutxlm_status: string;
    };
    recent: Array<{
      timestamp: string;
      filename: string;
      document_type: string;
      estimated_raw_error_rate: number;
      estimated_after_ai_error_rate: number;
      estimated_improvement_rate: number;
      quality_level: string;
      duration_ms: number;
    }>;
  };
  services: {
    llm?: {
      status?: string;
      provider?: string;
      model?: string;
    };
    layoutxlm?: {
      status?: string;
      model?: string;
      device?: string;
    };
  };
}

export function MonitoringDialog({ open, onOpenChange }: MonitoringDialogProps) {
  const [snapshot, setSnapshot] = useState<MonitoringSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const loadMonitoring = async () => {
    setIsLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/monitoring"));
      if (!response.ok) throw new Error("Khong the tai du lieu giam sat");
      setSnapshot(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Khong the tai du lieu giam sat");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    loadMonitoring();
    const timer = window.setInterval(loadMonitoring, 5000);
    return () => window.clearInterval(timer);
  }, [open]);

  const healthStatus = useMemo(() => {
    if (!snapshot) return "unknown";
    if (snapshot.api.error_rate >= 0.2 || snapshot.ocr.poor_rate >= 0.4) return "degraded";
    return "ok";
  }, [snapshot]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[86vh] overflow-y-auto sm:max-w-[900px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Activity className="size-5 text-blue-600" />
            Giám sát hệ thống
          </DialogTitle>
          <DialogDescription>
            Theo dõi độ trễ API, lỗi request, trạng thái dịch vụ và chất lượng OCR sau mỗi lần xử lý.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-3">
          <StatusBadge status={healthStatus} />
          <Button variant="outline" size="sm" onClick={loadMonitoring} disabled={isLoading}>
            <RefreshCw className={`mr-2 size-4 ${isLoading ? "animate-spin" : ""}`} />
            Làm mới
          </Button>
        </div>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {!snapshot ? (
          <div className="rounded-md border bg-card p-6 text-sm text-muted-foreground">
            Đang chờ dữ liệu giám sát...
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-4">
              <MetricCard
                icon={<Server className="size-4" />}
                label="Request"
                value={snapshot.api.requests_total.toString()}
                detail={`${formatRate(snapshot.api.error_rate)} lỗi`}
              />
              <MetricCard
                icon={<Clock3 className="size-4" />}
                label="P95 latency"
                value={`${Math.round(snapshot.api.latency_ms.p95)} ms`}
                detail={`Avg ${Math.round(snapshot.api.latency_ms.avg)} ms`}
              />
              <MetricCard
                icon={<Activity className="size-4" />}
                label="OCR runs"
                value={snapshot.ocr.runs_total.toString()}
                detail={`P95 ${Math.round(snapshot.ocr.duration_ms.p95)} ms`}
              />
              <MetricCard
                icon={<Sparkles className="size-4" />}
                label="AI cải thiện"
                value={formatRate(snapshot.ocr.average_improvement_rate)}
                detail={`${formatRate(snapshot.ocr.average_raw_error_rate)} -> ${formatRate(snapshot.ocr.average_after_ai_error_rate)}`}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-md border bg-card p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Chất lượng OCR</h3>
                  <Badge variant="outline">ước lượng</Badge>
                </div>
                <QualityRow
                  label="Lỗi trước AI"
                  value={snapshot.ocr.average_raw_error_rate}
                  tone="red"
                />
                <QualityRow
                  label="Lỗi sau AI"
                  value={snapshot.ocr.average_after_ai_error_rate}
                  tone="blue"
                />
                <QualityRow
                  label="Mức cải thiện"
                  value={snapshot.ocr.average_improvement_rate}
                  tone="green"
                />
                {snapshot.ocr.latest && (
                  <div className="mt-4 rounded-md bg-muted p-3 text-sm">
                    <div className="font-medium">{snapshot.ocr.latest.filename}</div>
                    <div className="mt-1 text-muted-foreground">
                      {snapshot.ocr.latest.document_type} · LLM {snapshot.ocr.latest.llm_status} · LayoutXLM {snapshot.ocr.latest.layoutxlm_status}
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-md border bg-card p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Dịch vụ</h3>
                  <Badge variant="outline">{formatDuration(snapshot.uptime_seconds)}</Badge>
                </div>
                <ServiceRow label="Backend" value="ready" />
                <ServiceRow label="LLM" value={snapshot.services.llm?.status || "unknown"} />
                <ServiceRow label="LayoutXLM" value={snapshot.services.layoutxlm?.status || "unknown"} />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <RecentList
                title="Request gần nhất"
                emptyText="Chưa có request."
                rows={snapshot.api.recent.map((item) => ({
                  key: `${item.timestamp}-${item.path}-${item.latency_ms}`,
                  title: `${item.method} ${item.path}`,
                  detail: `${item.status_code} · ${Math.round(item.latency_ms)} ms`,
                  tone: item.is_error ? "bad" : "good",
                }))}
              />
              <RecentList
                title="OCR gần nhất"
                emptyText="Chưa có lần OCR nào."
                rows={snapshot.ocr.recent.map((item) => ({
                  key: `${item.timestamp}-${item.filename}`,
                  title: item.filename,
                  detail: `${item.document_type} · ${formatRate(item.estimated_raw_error_rate)} -> ${formatRate(item.estimated_after_ai_error_rate)}`,
                  tone: item.quality_level === "poor" ? "bad" : "good",
                }))}
              />
            </div>

            <div className="flex items-start gap-2 rounded-md border bg-muted/60 p-3 text-xs text-muted-foreground">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              Tỷ lệ lỗi OCR là số ước lượng vận hành, không phải ground-truth. Hệ thống tính từ confidence của OCR, trường bắt buộc còn thiếu, cảnh báo và trạng thái AI sửa lỗi.
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="mb-3 flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-xs uppercase">{label}</span>
      </div>
      <div className="text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-sm text-muted-foreground">{detail}</div>
    </div>
  );
}

function QualityRow({ label, value, tone }: { label: string; value: number; tone: "red" | "blue" | "green" }) {
  const indicatorClass =
    tone === "red"
      ? "[&>div]:bg-red-500"
      : tone === "green"
        ? "[&>div]:bg-green-500"
        : "[&>div]:bg-blue-500";
  return (
    <div className="mb-3">
      <div className="mb-1 flex items-center justify-between text-sm">
        <span>{label}</span>
        <span className="font-medium">{formatRate(value)}</span>
      </div>
      <Progress value={Math.round(value * 100)} className={indicatorClass} />
    </div>
  );
}

function ServiceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b py-2 last:border-b-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <StatusBadge status={value} compact />
    </div>
  );
}

function RecentList({
  title,
  emptyText,
  rows,
}: {
  title: string;
  emptyText: string;
  rows: Array<{ key: string; title: string; detail: string; tone: "good" | "bad" }>;
}) {
  return (
    <div className="rounded-md border bg-card p-4">
      <h3 className="mb-3 text-sm font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <div className="text-sm text-muted-foreground">{emptyText}</div>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 8).map((row) => (
            <div key={row.key} className="flex items-start justify-between gap-3 rounded-md bg-muted/60 p-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{row.title}</div>
                <div className="text-xs text-muted-foreground">{row.detail}</div>
              </div>
              <span className={`mt-1 size-2 rounded-full ${row.tone === "bad" ? "bg-red-500" : "bg-green-500"}`} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status, compact = false }: { status: string; compact?: boolean }) {
  const normalized = status.toLowerCase();
  const isOk = ["ok", "ready", "enabled", "available"].includes(normalized);
  const isBad = ["error", "unavailable", "degraded", "poor"].includes(normalized);
  return (
    <Badge variant={isBad ? "destructive" : isOk ? "default" : "secondary"}>
      {compact ? status : `Trạng thái: ${status}`}
    </Badge>
  );
}

function formatRate(value: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${Math.round(seconds)}s uptime`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m uptime`;
  return `${Math.round(seconds / 3600)}h uptime`;
}
