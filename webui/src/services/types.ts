export type RunMode = "links" | "pdf" | "extract" | "pipeline";
export type RunStatus = "idle" | "running" | "paused" | "completed" | "failed" | "cancelling" | "cancelled";
export type StageStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export type StageName = "links" | "pdf" | "extract";
export type LogLevel = "DEBUG" | "INFO" | "WARN" | "ERROR";
export type PageKey = "command" | "workspace" | "links" | "pdf" | "extract" | "logs" | "history" | "about";

export interface WorkspaceSettings {
  projectRoot: string;
  annualReportDir: string;
  textOutputDir: string;
  stateDir: string;
  startYear: number;
  endYear: number;
}

export interface LinksSettings {
  seDate: string;
  pageSize: number;
  requestInterval: number;
  announcementConcurrency: number;
  marketScopes: string[];
  resetCheckpoint: boolean;
  deleteCheckpointOnSuccess: boolean;
}

export interface PdfSettings {
  downloadConcurrency: number;
}

export interface ExtractSettings {
  concurrency: number;
  resetCheckpoint: boolean;
  deleteCheckpointOnSuccess: boolean;
}

export interface AppSettings {
  workspace: WorkspaceSettings;
  links: LinksSettings;
  pdf: PdfSettings;
  extract: ExtractSettings;
}

export interface NotificationPrefs {
  desktopEnabled: boolean;
  soundEnabled: boolean;
  permission: NotificationPermission | "unsupported";
}

export interface ProgressState {
  current: number;
  total: number;
  percent: number;
}

export interface StageState {
  name: StageName;
  title: string;
  status: StageStatus;
  progress: ProgressState;
  result: Record<string, any> | null;
  hint: string;
}

export interface LogItem {
  time: string;
  level: LogLevel;
  stage: StageName | "system";
  message: string;
}

export interface RunSummary {
  links: Record<string, any> | null;
  pdf: Record<string, any> | null;
  extract: Record<string, any> | null;
}

export interface RunState {
  runId: string | null;
  mode: RunMode | null;
  status: RunStatus;
  currentStage: StageName | null;
  startedAt: string | null;
  finishedAt: string | null;
  summary: RunSummary;
  error: string | null;
  outputs?: Record<string, string>;
}

export interface IncrementalYearBucket {
  year: number;
  status: string;
  [key: string]: any;
}

export interface IncrementalStatus {
  mode: "incremental";
  enabled: boolean;
  description: string;
  range: {
    startYear: number;
    endYear: number;
    yearTotal: number;
  };
  workspace: {
    projectRoot: string;
    annualReportDir: string;
    textOutputDir: string;
    stateDir: string;
  };
  links: {
    completedYears: number;
    partialYears?: number;
    pendingYears: number;
    totalRows: number;
    checkpointPath: string;
    checkpointExists: boolean;
    checkpointTrackedYears?: number;
    yearBuckets: IncrementalYearBucket[];
  };
  pdf: {
    targetTotal: number;
    existingTotal: number;
    skippedTotal: number;
    pendingTotal: number;
    summaryPath?: string;
    summaryExists?: boolean;
    summaryTrackedYears?: number;
    yearBuckets: IncrementalYearBucket[];
  };
  extract: {
    pdfTotal: number;
    existingTotal: number;
    pendingTotal: number;
    checkpointCompletedTotal?: number;
    checkpointFailedTotal?: number;
    checkpointPath: string;
    checkpointExists: boolean;
    checkpointJobKey?: string | null;
    summaryPath?: string;
    summaryExists?: boolean;
    summaryStats?: Record<string, any> | null;
    yearBuckets: IncrementalYearBucket[];
  };
}

export interface HistoryItem {
  runId: string;
  mode: RunMode;
  status: RunStatus;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  outputDir: string;
  outputDirectories: Record<string, string>;
  settingsSnapshot?: AppSettings | null;
  summary: RunSummary;
  stages: StageState[];
}

export interface VisualizationIndexYearBucket {
  year: number;
  total?: number;
  completed?: number;
  count?: number;
  status?: string;
  active?: boolean;
  [key: string]: any;
}

export interface VisualizationIndexLinksSnapshot {
  yearTotal: number;
  currentYearIndex: number;
  currentYear: number | null;
  rangeCurrent: number;
  rangeTotal: number;
  recordsFound: number;
  rawRecordsFound: number;
  currentWindow: string;
  overallPercent: number;
  totalAnnouncements: number;
  countBasis?: string;
  yearBuckets: VisualizationIndexYearBucket[];
}

export interface VisualizationIndexSnapshot {
  links: VisualizationIndexLinksSnapshot;
  pdf: {
    yearBuckets: VisualizationIndexYearBucket[];
    total: number;
    completed: number;
    speedPerMinute?: number;
    etaSeconds?: number;
  };
  extract: {
    yearBuckets: VisualizationIndexYearBucket[];
    total: number;
    completed: number;
    speedPerMinute?: number;
    etaSeconds?: number;
  };
  meta: Record<string, any>;
}

export interface RuntimeSnapshot {
  activeRunId: string | null;
  status: RunStatus;
  windowReady: boolean;
}

export interface RunSnapshot {
  runId: string;
  mode: RunMode;
  status: RunStatus;
  currentStage: StageName | null;
  startedAt: string | null;
  finishedAt: string | null;
  summary: RunSummary;
  error: string | null;
  outputs?: Record<string, string>;
}

export interface StageSnapshotResponse {
  items: StageState[];
}

export interface LogSnapshotResponse {
  items: LogItem[];
}

export interface HistorySnapshotResponse {
  items: HistoryItem[];
}

export interface UpdateCheckResult {
  status: "available" | "current" | "error";
  currentVersion: string;
  latestVersion: string;
  downloadUrl: string;
  downloadFileName: string;
  downloadChannel: string;
  notes: string[];
  force: boolean;
  sha256: string;
  sourceUrl: string;
  message?: string;
  attempts?: Array<{ url: string; error: string }>;
  raw?: Record<string, any>;
}

export interface ApiError {
  code: string;
  message: string;
}

export interface ApiResult<T> {
  ok: boolean;
  data?: T;
  error?: ApiError;
}
