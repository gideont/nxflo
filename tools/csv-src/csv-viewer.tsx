"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minimize2,
  FileText,
  Download,
  Eraser,
  Moon,
  Palette,
  Sun,
  Upload,
  X
} from "lucide-react";
import Papa, { type ParseError, type Parser, type ParseResult } from "papaparse";
import {
  type ChangeEvent,
  type CSSProperties,
  type DragEvent,
  type PointerEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState
} from "react";
import * as XLSX from "xlsx";

type CsvRow = string[];

type ParsedCsv = {
  fileName: string;
  headers: string[];
  sourceHeaders: string[];
  exportRows: CsvRow[];
  rows: CsvRow[];
  columnWidths: number[];
};

type PendingWorkbook = {
  fileName: string;
  workbook: XLSX.WorkBook;
  sheetNames: string[];
};

type SortState = {
  columnIndex: number;
  direction: "asc" | "desc";
} | null;

const DEFAULT_HEADER_COLOR = "#225ee8";
const APP_VERSION = "0.1.0";
const MIN_COLUMN_WIDTH = 112;
const DEFAULT_MAX_COLUMN_WIDTH = 360;
const MAX_COLUMN_WIDTH_LIMIT = 720;
const CELL_HORIZONTAL_PADDING = 32;
const SAMPLE_ROW_LIMIT = 250;
const ROW_HEIGHTS = {
  compact: 30,
  comfortable: 42
} as const;
const ROWS_PER_PAGE_OPTIONS = [25, 50, 100, 250, 500] as const;
const DEFAULT_ROWS_PER_PAGE = 100;
const PARSE_CHUNK_SIZE = 1024 * 1024;
const CHUNK_PAUSE_MS = 0;
const SUPPORTED_FILE_ACCEPT =
  ".csv,text/csv,.xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel";

type RowDensity = keyof typeof ROW_HEIGHTS;
type RowsPerPage = (typeof ROWS_PER_PAGE_OPTIONS)[number];

function normalizeValue(value: unknown) {
  if (value === null || value === undefined) {
    return "";
  }

  return String(value);
}

function getReadableHeader(rawHeader: string, index: number) {
  const trimmed = rawHeader.trim();
  return trimmed.length > 0 ? trimmed : `Column ${index + 1}`;
}

function estimateColumnWidths(headers: string[], rows: CsvRow[], maxColumnWidth: number) {
  return headers.map((header, columnIndex) => {
    const sampledRows = rows.slice(0, SAMPLE_ROW_LIMIT);
    const maxCharacters = sampledRows.reduce((max, row) => {
      return Math.max(max, normalizeValue(row[columnIndex]).length);
    }, header.length);

    return Math.max(
      MIN_COLUMN_WIDTH,
      Math.min(maxColumnWidth, maxCharacters * 8 + CELL_HORIZONTAL_PADDING)
    );
  });
}

function getParseErrorMessage(errors: ParseError[]) {
  if (errors.length === 0) {
    return "We could not parse this CSV. Check the file format and try again.";
  }

  const firstError = errors[0];
  const rowMessage =
    typeof firstError.row === "number" ? ` near row ${firstError.row + 1}` : "";

  return `${firstError.message}${rowMessage}.`;
}

function normalizeCsvRows(rows: unknown[][]) {
  return rows
    .map((row) => row.map(normalizeValue))
    .filter((row) => row.some((cell) => cell.trim().length > 0));
}

function buildParsedCsvFromRows(
  fileName: string,
  rawRows: unknown[][],
  maxColumnWidth: number
): ParsedCsv {
  const rows = normalizeCsvRows(rawRows);

  if (rows.length === 0) {
    throw new Error("This CSV is empty. Choose a file with a header row and data.");
  }

  const [rawHeaders, ...rawDataRows] = rows;
  const headers = rawHeaders.map(getReadableHeader);

  if (headers.length === 0 || headers.every((header) => header.trim().length === 0)) {
    throw new Error("This CSV does not include a usable header row.");
  }

  if (rawDataRows.length === 0) {
    throw new Error("This CSV only has a header row. Add at least one data row.");
  }

  const columnCount = headers.length;
  const dataRows = rawDataRows.map((row) => {
    if (row.length === columnCount) {
      return row;
    }

    if (row.length > columnCount) {
      return row.slice(0, columnCount);
    }

    return [...row, ...Array<string>(columnCount - row.length).fill("")];
  });

  return {
    fileName,
    headers,
    sourceHeaders: rawHeaders,
    exportRows: rawDataRows,
    rows: dataRows,
    columnWidths: estimateColumnWidths(headers, dataRows, maxColumnWidth)
  };
}

function hasExcelExtension(fileName: string) {
  return /\.(xlsx|xls)$/i.test(fileName);
}

function isExcelFile(file: File) {
  return hasExcelExtension(file.name);
}

function isCsvFile(file: File) {
  return /\.csv$/i.test(file.name) || file.type === "text/csv";
}

function parseCsvFile(
  file: File,
  maxColumnWidth: number,
  onProgress: (rowCount: number) => void
): Promise<ParsedCsv> {
  return new Promise((resolve, reject) => {
    const rawRows: unknown[][] = [];
    const errors: ParseError[] = [];

    Papa.parse<unknown[]>(file, {
      worker: false,
      skipEmptyLines: "greedy",
      dynamicTyping: false,
      chunkSize: PARSE_CHUNK_SIZE,
      chunk: (result: ParseResult<unknown[]>, parser: Parser) => {
        if (result.errors.length > 0) {
          errors.push(...result.errors);
          parser.abort();
          return;
        }

        rawRows.push(...result.data);
        onProgress(Math.max(0, rawRows.length - 1));

        parser.pause();
        window.setTimeout(() => parser.resume(), CHUNK_PAUSE_MS);
      },
      complete: (result) => {
        if (result.errors.length > 0) {
          errors.push(...result.errors);
        }

        if (errors.length > 0) {
          reject(new Error(getParseErrorMessage(errors)));
          return;
        }

        try {
          resolve(buildParsedCsvFromRows(file.name, rawRows, maxColumnWidth));
        } catch (error) {
          reject(error);
        }
      },
      error: (error) => {
        reject(new Error(error.message));
      }
    });
  });
}

function SortIcon({ direction }: { direction: false | "asc" | "desc" }) {
  if (direction === "asc") {
    return <ArrowUp aria-hidden="true" className="h-4 w-4" />;
  }

  if (direction === "desc") {
    return <ArrowDown aria-hidden="true" className="h-4 w-4" />;
  }

  return <ArrowUpDown aria-hidden="true" className="h-4 w-4 opacity-70" />;
}

export function CsvViewer() {
  const [parsedCsv, setParsedCsv] = useState<ParsedCsv | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("light");
  const [headerColor, setHeaderColor] = useState(DEFAULT_HEADER_COLOR);
  const [sorting, setSorting] = useState<SortState>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorTitle, setErrorTitle] = useState("Unable to load file");
  const [sheetSelectionError, setSheetSelectionError] = useState<string | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [pendingFileName, setPendingFileName] = useState<string | null>(null);
  const [parsedRowCount, setParsedRowCount] = useState(0);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [isSummaryCollapsed, setIsSummaryCollapsed] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState("");
  const [maxColumnWidth, setMaxColumnWidth] = useState(DEFAULT_MAX_COLUMN_WIDTH);
  const [rowDensity, setRowDensity] = useState<RowDensity>("comfortable");
  const [rowsPerPage, setRowsPerPage] = useState<RowsPerPage>(DEFAULT_ROWS_PER_PAGE);
  const [currentPage, setCurrentPage] = useState(1);
  const [pendingWorkbook, setPendingWorkbook] = useState<PendingWorkbook | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const tableViewportRef = useRef<HTMLDivElement | null>(null);
  const rowHeight = ROW_HEIGHTS[rowDensity];

  useLayoutEffect(() => {
    const shell = document.getElementById("csv-viewer")?.closest(".csv-viewer-shell");
    const root = document.documentElement;
    const previousScroll = window.scrollY;
    shell?.classList.toggle("is-expanded", isExpanded);
    root.classList.toggle("csv-expanded", isExpanded);
    if (!isExpanded) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.querySelector(".csv-dialog")) setIsExpanded(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      shell?.classList.remove("is-expanded");
      root.classList.remove("csv-expanded");
      window.scrollTo({ top: previousScroll, behavior: "instant" });
    };
  }, [isExpanded]);

  const sortedRows = useMemo(() => {
    if (!parsedCsv) {
      return [];
    }

    if (!sorting) {
      return parsedCsv.rows;
    }

    const collator = new Intl.Collator(undefined, {
      numeric: true,
      sensitivity: "base"
    });

    return [...parsedCsv.rows].sort((leftRow, rightRow) => {
      const leftValue = leftRow[sorting.columnIndex] ?? "";
      const rightValue = rightRow[sorting.columnIndex] ?? "";
      const result = collator.compare(leftValue, rightValue);
      return sorting.direction === "asc" ? result : -result;
    });
  }, [parsedCsv, sorting]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / rowsPerPage));
  const activePage = Math.min(currentPage, totalPages);
  const pageStartIndex = (activePage - 1) * rowsPerPage;
  const pageRows = useMemo(
    () => sortedRows.slice(pageStartIndex, pageStartIndex + rowsPerPage),
    [pageStartIndex, rowsPerPage, sortedRows]
  );
  const shouldShowPagination = sortedRows.length > rowsPerPage;

  const rowVirtualizer = useVirtualizer({
    count: pageRows.length,
    getScrollElement: () => tableViewportRef.current,
    estimateSize: () => rowHeight,
    overscan: 12
  });

  useEffect(() => {
    rowVirtualizer.measure();
  }, [rowHeight, rowVirtualizer]);

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  useEffect(() => {
    tableViewportRef.current?.scrollTo({ top: 0 });
  }, [activePage, rowsPerPage, sorting]);

  const totalWidth = parsedCsv
    ? parsedCsv.columnWidths.reduce((sum, width) => sum + width, 0)
    : 0;

  const gridTemplateColumns = parsedCsv
    ? parsedCsv.columnWidths.map((width) => `${width}px`).join(" ")
    : "";

  function updateMaxColumnWidth(nextMaxColumnWidth: number) {
    const clampedMaxColumnWidth = Math.max(
      MIN_COLUMN_WIDTH,
      Math.min(MAX_COLUMN_WIDTH_LIMIT, nextMaxColumnWidth)
    );

    setMaxColumnWidth(clampedMaxColumnWidth);
    setParsedCsv((currentCsv) => {
      if (!currentCsv) {
        return currentCsv;
      }

      return {
        ...currentCsv,
        columnWidths: currentCsv.columnWidths.map((width) =>
          Math.max(MIN_COLUMN_WIDTH, Math.min(clampedMaxColumnWidth, width))
        )
      };
    });
  }

  function resizeColumn(columnIndex: number, nextWidth: number) {
    setParsedCsv((currentCsv) => {
      if (!currentCsv) {
        return currentCsv;
      }

      return {
        ...currentCsv,
        columnWidths: currentCsv.columnWidths.map((width, index) =>
          index === columnIndex
            ? Math.max(MIN_COLUMN_WIDTH, Math.min(maxColumnWidth, nextWidth))
            : width
        )
      };
    });
  }

  function startColumnResize(
    event: PointerEvent<HTMLSpanElement>,
    columnIndex: number
  ) {
    if (!parsedCsv) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const startX = event.clientX;
    const startWidth = parsedCsv.columnWidths[columnIndex] ?? MIN_COLUMN_WIDTH;

    function handlePointerMove(pointerEvent: globalThis.PointerEvent) {
      resizeColumn(columnIndex, startWidth + pointerEvent.clientX - startX);
    }

    function handlePointerUp() {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
  }

  async function loadCsvFile(file: File) {
    if (!file) {
      return;
    }

    setIsParsing(true);
    setPendingFileName(file.name);
    setParsedRowCount(0);
    setParsedCsv(null);
    setErrorMessage(null);
    setErrorTitle("Unable to load file");
    setSheetSelectionError(null);
    setSorting(null);
    setCurrentPage(1);
    setPendingWorkbook(null);

    await new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => resolve());
    });

    try {
      const nextCsv = await parseCsvFile(file, maxColumnWidth, setParsedRowCount);
      setParsedCsv(nextCsv);
    } catch (error) {
      setParsedCsv(null);
      setErrorTitle("Unable to load file");
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Something went wrong while reading this CSV."
      );
    } finally {
      setIsParsing(false);
      setPendingFileName(null);
      setParsedRowCount(0);
    }
  }

  async function loadExcelFile(file: File) {
    if (!file) {
      return;
    }

    setIsParsing(true);
    setPendingFileName(file.name);
    setParsedRowCount(0);
    setParsedCsv(null);
    setErrorMessage(null);
    setErrorTitle("Unable to load file");
    setSheetSelectionError(null);
    setSorting(null);
    setCurrentPage(1);
    setPendingWorkbook(null);

    await new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => resolve());
    });

    try {
      const buffer = await file.arrayBuffer();
      const workbook = XLSX.read(buffer, { type: "array" });
      const sheetNames = workbook.SheetNames;

      if (sheetNames.length === 0) {
        throw new Error("This Excel file does not contain any sheets.");
      }

      setPendingWorkbook({
        fileName: file.name,
        workbook,
        sheetNames
      });
    } catch (error) {
      setPendingWorkbook(null);
      setErrorTitle("Unable to load file");
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Something went wrong while reading this Excel file."
      );
    } finally {
      setIsParsing(false);
      setPendingFileName(null);
      setParsedRowCount(0);
    }
  }

  function loadExcelSheet(sheetName: string) {
    if (!pendingWorkbook) {
      return;
    }

    const worksheet = pendingWorkbook.workbook.Sheets[sheetName];

    if (!worksheet) {
      setSheetSelectionError(`Could not find the "${sheetName}" sheet.`);
      return;
    }

    try {
      const rows = XLSX.utils.sheet_to_json<unknown[]>(worksheet, {
        header: 1,
        raw: false,
        defval: ""
      });

      setParsedCsv(
        buildParsedCsvFromRows(
          `${pendingWorkbook.fileName} · ${sheetName}`,
          rows,
          maxColumnWidth
        )
      );
      setPendingWorkbook(null);
      setErrorMessage(null);
      setErrorTitle("Unable to load file");
      setSheetSelectionError(null);
      setSorting(null);
      setCurrentPage(1);
    } catch (error) {
      setParsedCsv(null);
      const message = error instanceof Error ? error.message : "";
      const sheetLabel = `"${sheetName}" sheet`;

      if (message.includes("empty")) {
        setSheetSelectionError(
          `${sheetLabel} is empty. Choose another sheet with a header row and data.`
        );
        return;
      }

      if (message.includes("only has a header row")) {
        setSheetSelectionError(
          `${sheetLabel} only has a header row. Choose another sheet with data rows.`
        );
        return;
      }

      if (message.includes("usable header")) {
        setSheetSelectionError(
          `${sheetLabel} does not include a usable header row. Choose another sheet with tabular data.`
        );
        return;
      }

      setSheetSelectionError(
        `Something went wrong while reading the "${sheetName}" sheet.`
      );
    }
  }

  async function loadFile(file: File) {
    if (isParsing) return;
    setCleanupMessage("");
    if (isExcelFile(file)) {
      await loadExcelFile(file);
      return;
    }

    if (isCsvFile(file)) {
      await loadCsvFile(file);
      return;
    }

    setParsedCsv(null);
    setPendingWorkbook(null);
    setErrorTitle("Unsupported file type");
    setSheetSelectionError(null);
    setErrorMessage("Choose a CSV or Excel file with a .csv, .xlsx, or .xls extension.");
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (file) {
      await loadFile(file);
    }

    event.target.value = "";
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsDraggingFile(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setIsDraggingFile(false);
    }
  }

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDraggingFile(false);

    const file = event.dataTransfer.files?.[0];

    if (!file) {
      return;
    }

    await loadFile(file);
  }

  function clearCsv() {
    setCleanupMessage("");
    setParsedCsv(null);
    setSorting(null);
    setErrorMessage(null);
    setErrorTitle("Unable to load file");
    setSheetSelectionError(null);
    setPendingFileName(null);
    setParsedRowCount(0);
    setCurrentPage(1);
    setPendingWorkbook(null);
  }

  function clearNullValues() {
    if (!parsedCsv) return;
    let count = 0;
    const clean = (value: string) => value.trim().toLowerCase() === "null" ? "" : value;
    const exportRows = parsedCsv.exportRows.map((row) => row.map((value) => {
      if (value.trim().toLowerCase() === "null") { count += 1; return ""; }
      return value;
    }));
    setParsedCsv({ ...parsedCsv, exportRows, rows: parsedCsv.rows.map((row) => row.map(clean)) });
    setCleanupMessage(count
      ? `Replaced ${count.toLocaleString()} NULL ${count === 1 ? "cell" : "cells"} with blanks. Cleaned CSV is ready to download.`
      : "No NULL values found. Your CSV is ready to download.");
  }

  function downloadCleanedCsv() {
    if (!parsedCsv || !cleanupMessage) return;
    // Export every source row in its original order, independent of sorting or pagination.
    const csv = Papa.unparse([parsedCsv.sourceHeaders, ...parsedCsv.exportRows], { newline: "\r\n" });
    const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = parsedCsv.fileName.replace(/\.(csv|xlsx|xls)(?=\s*·|$)/i, "").replace(/[\\/:*?"<>|\x00-\x1f]/g, "_") + "-cleaned.csv";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function toggleSort(columnIndex: number) {
    setSorting((currentSort) => {
      if (!currentSort || currentSort.columnIndex !== columnIndex) {
        return { columnIndex, direction: "asc" };
      }

      return {
        columnIndex,
        direction: currentSort.direction === "asc" ? "desc" : "asc"
      };
    });
    setCurrentPage(1);
  }

  function updateRowsPerPage(nextRowsPerPage: RowsPerPage) {
    setRowsPerPage(nextRowsPerPage);
    setCurrentPage(1);
  }

  useLayoutEffect(() => {
    if (!pendingWorkbook) return;
    const previous = document.activeElement as HTMLElement;
    const dialog = document.querySelector<HTMLElement>(".csv-dialog");
    const buttons = () => Array.from(dialog?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    buttons()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); clearCsv(); }
      if (event.key === "Tab") {
        const targets = buttons();
        if (event.shiftKey && document.activeElement === targets[0]) {
          event.preventDefault(); targets[targets.length - 1]?.focus();
        } else if (!event.shiftKey && document.activeElement === targets[targets.length - 1]) {
          event.preventDefault(); targets[0]?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); previous?.focus(); };
  }, [pendingWorkbook]);

  const isDark = theme === "dark";
  const isReadingExcel = pendingFileName ? hasExcelExtension(pendingFileName) : false;

  return (
    <div
      className={clsx(
        isDark && "dark",
        "csv-workspace transition-colors",
        isExpanded && "is-expanded",
        isDark ? "bg-[#0c192c] text-[#f4f7f2]" : "bg-paper text-ink"
      )}
    >
      <section className="mx-auto flex w-full min-w-0 flex-col gap-5">
        <div className="flex flex-col gap-4 border-b border-ink/10 pb-5 dark:border-white/10 lg:flex-row lg:items-end lg:justify-between">
          <div className="csv-main-actions flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() =>
                setTheme((currentTheme) =>
                  currentTheme === "dark" ? "light" : "dark"
                )
              }
              className="inline-flex min-h-11 items-center gap-2 rounded-md border border-ink/15 bg-white px-4 py-2.5 text-sm font-semibold text-ink transition hover:border-moss hover:text-moss dark:border-white/15 dark:bg-white/10 dark:text-white dark:hover:border-gold dark:hover:text-gold"
              aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
            >
              {isDark ? (
                <Sun aria-hidden="true" className="h-4 w-4" />
              ) : (
                <Moon aria-hidden="true" className="h-4 w-4" />
              )}
              {isDark ? "Light mode" : "Dark mode"}
            </button>

            <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-md bg-ink px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-moss focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-gold dark:bg-gold dark:text-ink dark:hover:bg-white">
              <Upload aria-hidden="true" className="h-4 w-4" />
              <span>Upload file</span>
              <input
                ref={fileInputRef}
                className="sr-only"
                type="file"
                accept={SUPPORTED_FILE_ACCEPT}
                disabled={isParsing}
                onChange={handleFileChange}
              />
            </label>

            <button
              type="button"
              className="csv-expand-button inline-flex min-h-11 items-center gap-2 rounded-md border border-ink/15 bg-white px-4 py-2.5 text-sm font-semibold text-ink transition hover:border-moss hover:text-moss dark:border-white/15 dark:bg-white/10 dark:text-white dark:hover:border-gold dark:hover:text-gold"
              onClick={() => setIsExpanded((expanded) => !expanded)}
              aria-pressed={isExpanded}
              aria-controls="csv-data-panel"
              title={isExpanded ? "Restore the normal table size" : "Expand the table to the browser width and height"}
            >
              {isExpanded ? <Minimize2 aria-hidden="true" className="h-4 w-4" /> : <Maximize2 aria-hidden="true" className="h-4 w-4" />}
              {isExpanded ? "Restore table size" : "Expand table"}
            </button>

            <button type="button" onClick={clearNullValues} disabled={!parsedCsv || isParsing}
              title="Replace cells containing NULL or null with blanks. Other values and column headers are preserved."
              className="csv-clean-button inline-flex min-h-11 items-center gap-2 rounded-md border border-ink/15 bg-white px-4 py-2.5 text-sm font-semibold text-ink disabled:opacity-45 dark:border-white/15 dark:bg-white/10 dark:text-white">
              <Eraser aria-hidden="true" className="h-4 w-4" /> Clear NULL values
            </button>
            <button type="button" onClick={downloadCleanedCsv} disabled={!parsedCsv || !cleanupMessage || isParsing}
              className="inline-flex min-h-11 items-center gap-2 rounded-md border border-ink/15 bg-white px-4 py-2.5 text-sm font-semibold text-ink disabled:opacity-45 dark:border-white/15 dark:bg-white/10 dark:text-white">
              <Download aria-hidden="true" className="h-4 w-4" /> Download cleaned CSV
            </button>

            {parsedCsv || pendingWorkbook ? (
              <button
                type="button"
                onClick={clearCsv}
                className="inline-flex min-h-11 items-center gap-2 rounded-md border border-ink/15 bg-white px-4 py-2.5 text-sm font-semibold text-ink transition hover:border-coral hover:text-coral dark:border-white/15 dark:bg-white/10 dark:text-white dark:hover:border-coral dark:hover:text-coral"
              >
                <X aria-hidden="true" className="h-4 w-4" />
                Clear
              </button>
            ) : null}
          </div>
          {cleanupMessage && <p className="csv-clean-status text-sm" role="status">{cleanupMessage}</p>}
        </div>

        <div
          className={clsx(
            "csv-layout",
            isSummaryCollapsed
              ? "is-collapsed"
              : ""
          )}
        >
          <div
            id="csv-data-panel"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={clsx(
              "flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border bg-white shadow-soft transition dark:bg-[#13253e]",
              isDraggingFile
                ? "border-gold ring-2 ring-gold/40"
                : "border-ink/10 dark:border-white/10"
            )}
          >
            <div className="csv-toolbar flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-ink/10 px-4 py-3 dark:border-white/10">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-gold/20 text-ink dark:text-gold">
                  <FileText aria-hidden="true" className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink dark:text-white">
                    {pendingFileName ??
                      parsedCsv?.fileName ??
                      pendingWorkbook?.fileName ??
                      "No file loaded"}
                  </p>
                  <p className="text-sm text-ink/60 dark:text-white/60">
                    {isParsing
                      ? isReadingExcel
                        ? "Reading workbook sheets in your browser..."
                        : `Parsing in your browser... ${parsedRowCount.toLocaleString()} rows read`
                      : parsedCsv
                        ? `${parsedCsv.rows.length.toLocaleString()} rows, ${parsedCsv.headers.length.toLocaleString()} columns`
                        : pendingWorkbook
                          ? `${pendingWorkbook.sheetNames.length.toLocaleString()} sheet${pendingWorkbook.sheetNames.length === 1 ? "" : "s"} found. Choose one sheet to display.`
                        : isDraggingFile
                          ? "Drop the CSV or Excel file to load it."
                          : "Upload or drop a CSV or Excel file to begin."}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div className="flex items-center gap-3 rounded-md border border-ink/10 bg-paper px-3 py-2 dark:border-white/10 dark:bg-white/5">
                  <Palette aria-hidden="true" className="h-4 w-4 text-moss" />
                  <label
                    htmlFor="header-color"
                    className="text-sm font-medium text-ink/80 dark:text-white/80"
                  >
                    Header
                  </label>
                  <input
                    id="header-color"
                    aria-label="Table header background color"
                    type="color"
                    value={headerColor}
                    onChange={(event) => setHeaderColor(event.target.value)}
                    className="h-8 w-10 cursor-pointer rounded border border-ink/10 bg-transparent p-0 dark:border-white/20"
                  />
                </div>

                <div className="flex items-center gap-3 rounded-md border border-ink/10 bg-paper px-3 py-2 dark:border-white/10 dark:bg-white/5">
                  <label
                    htmlFor="max-column-width"
                    className="text-sm font-medium text-ink/80 dark:text-white/80"
                  >
                    Max col
                  </label>
                  <input
                    id="max-column-width"
                    aria-label="Maximum column width"
                    type="range"
                    min={MIN_COLUMN_WIDTH}
                    max={MAX_COLUMN_WIDTH_LIMIT}
                    step={8}
                    value={maxColumnWidth}
                    onChange={(event) =>
                      updateMaxColumnWidth(Number(event.target.value))
                    }
                    className="h-8 w-28 accent-moss dark:accent-gold"
                  />
                  <output
                    htmlFor="max-column-width"
                    className="min-w-12 text-right text-sm font-semibold text-ink dark:text-white"
                  >
                    {maxColumnWidth}px
                  </output>
                </div>

                <div className="inline-flex rounded-md border border-ink/10 bg-paper p-1 dark:border-white/10 dark:bg-white/5">
                  {(["compact", "comfortable"] as RowDensity[]).map((density) => (
                    <button
                      key={density}
                      type="button"
                      onClick={() => setRowDensity(density)}
                      className={clsx(
                        "h-8 rounded px-3 text-sm font-semibold capitalize transition",
                        rowDensity === density
                          ? "bg-ink text-white dark:bg-gold dark:text-ink"
                          : "text-ink/70 hover:text-ink dark:text-white/70 dark:hover:text-white"
                      )}
                      aria-pressed={rowDensity === density}
                    >
                      {density}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-3 rounded-md border border-ink/10 bg-paper px-3 py-2 dark:border-white/10 dark:bg-white/5">
                  <label
                    htmlFor="rows-per-page"
                    className="text-sm font-medium text-ink/80 dark:text-white/80"
                  >
                    Rows/page
                  </label>
                  <select
                    id="rows-per-page"
                    aria-label="Rows per page"
                    value={rowsPerPage}
                    onChange={(event) =>
                      updateRowsPerPage(Number(event.target.value) as RowsPerPage)
                    }
                    className="h-8 rounded border border-ink/10 bg-white px-2 text-sm font-semibold text-ink dark:border-white/20 dark:bg-[#13253e] dark:text-white"
                  >
                    {ROWS_PER_PAGE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>

                {shouldShowPagination ? (
                  <div className="flex items-center gap-2 rounded-md border border-ink/10 bg-paper px-2 py-2 dark:border-white/10 dark:bg-white/5">
                    <button
                      type="button"
                      onClick={() =>
                        setCurrentPage((page) => Math.max(1, page - 1))
                      }
                      disabled={activePage === 1}
                      className="inline-flex h-8 w-8 items-center justify-center rounded border border-ink/10 bg-white text-ink transition hover:border-moss hover:text-moss disabled:cursor-not-allowed disabled:opacity-45 dark:border-white/10 dark:bg-[#13253e] dark:text-white dark:hover:border-gold dark:hover:text-gold"
                      aria-label="Previous page"
                      title="Previous page"
                    >
                      <ChevronLeft aria-hidden="true" className="h-4 w-4" />
                    </button>
                    <span className="min-w-24 text-center text-sm font-semibold text-ink dark:text-white">
                      Page {activePage.toLocaleString()} of{" "}
                      {totalPages.toLocaleString()}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setCurrentPage((page) => Math.min(totalPages, page + 1))
                      }
                      disabled={activePage === totalPages}
                      className="inline-flex h-8 w-8 items-center justify-center rounded border border-ink/10 bg-white text-ink transition hover:border-moss hover:text-moss disabled:cursor-not-allowed disabled:opacity-45 dark:border-white/10 dark:bg-[#13253e] dark:text-white dark:hover:border-gold dark:hover:text-gold"
                      aria-label="Next page"
                      title="Next page"
                    >
                      <ChevronRight aria-hidden="true" className="h-4 w-4" />
                    </button>
                  </div>
                ) : null}
              </div>

            </div>

            {errorMessage ? (
              <div role="alert" className="m-4 flex items-start gap-3 rounded-md border border-coral/25 bg-coral/10 p-4 text-coral dark:bg-coral/15">
                <AlertCircle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
                <div>
                  <p className="font-semibold">{errorTitle}</p>
                  <p className="mt-1 text-sm leading-6 text-ink/75 dark:text-white/75">{errorMessage}</p>
                </div>
              </div>
            ) : null}

            {!parsedCsv && !errorMessage && !pendingWorkbook ? (
              <div className="flex min-h-0 flex-1 items-center justify-center px-6 py-12 text-center">
                <div className="max-w-md">
                  <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-lg bg-moss/10 text-moss dark:bg-gold/15 dark:text-gold">
                    <Upload aria-hidden="true" className="h-7 w-7" />
                  </div>
                  <h2 className="mt-5 text-xl font-semibold text-ink dark:text-white">
                    Drop a CSV or Excel file here
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-ink/65 dark:text-white/65">
                    Or use Upload file. CSV and Excel files are processed locally;
                    the first row of the selected data becomes the header.
                  </p>
                </div>
              </div>
            ) : null}

            {isParsing ? (
              <div className="m-4 overflow-hidden rounded-md border border-gold/30 bg-gold/10">
                <div className="h-1.5 w-full animate-pulse bg-gold" />
                <p className="px-4 py-3 text-sm font-medium text-ink/75 dark:text-white/75">
                  Reading and validating the CSV... {parsedRowCount.toLocaleString()} rows read
                </p>
              </div>
            ) : null}

            {parsedCsv ? (
              <div
                ref={tableViewportRef}
                className="csv-viewport"
                role="table" aria-label="Uploaded data" tabIndex={0}
              >
                <div
                  style={{ minWidth: totalWidth }}
                  className="min-h-full w-full"
                >
                  <div
                    role="row"
                    className="sticky top-0 z-10 grid border-b border-ink/10 text-left text-sm font-semibold text-white shadow-sm dark:border-white/10"
                    style={
                      {
                        gridTemplateColumns,
                        backgroundColor: headerColor
                      } as CSSProperties
                    }
                  >
                    {parsedCsv.headers.map((header, columnIndex) => {
                      const sortedDirection =
                        sorting?.columnIndex === columnIndex
                          ? sorting.direction
                          : false;

                      return (
                        <button
                          key={`${header}-${columnIndex}`}
                          type="button"
                          role="columnheader"
                          aria-sort={sortedDirection === "asc" ? "ascending" : sortedDirection === "desc" ? "descending" : "none"}
                          onClick={() => toggleSort(columnIndex)}
                          className="group relative flex h-12 min-w-0 items-center justify-between gap-2 border-r border-white/15 px-3 text-left transition hover:bg-black/10 focus:outline focus:outline-2 focus:outline-offset-[-2px] focus:outline-white"
                          title={header}
                        >
                          <span className="truncate">{header}</span>
                          <SortIcon direction={sortedDirection} />
                          <span
                            role="separator"
                            aria-orientation="vertical"
                            aria-label={`Resize ${header} column`}
                            tabIndex={0}
                            onKeyDown={(event) => {
                              if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
                                event.preventDefault(); event.stopPropagation();
                                resizeColumn(columnIndex, parsedCsv.columnWidths[columnIndex] + (event.key === "ArrowRight" ? 16 : -16));
                              }
                            }}
                            onPointerDown={(event) =>
                              startColumnResize(event, columnIndex)
                            }
                            onClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                            }}
                            className="absolute inset-y-0 right-0 z-20 w-2 cursor-col-resize touch-none bg-white/0 transition group-hover:bg-white/30"
                          />
                        </button>
                      );
                    })}
                  </div>

                  <div
                    className="relative"
                    style={{ height: rowVirtualizer.getTotalSize() }}
                  >
                    {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                      const row = pageRows[virtualRow.index];
                      const absoluteRowIndex = pageStartIndex + virtualRow.index;

                      return (
                        <div
                          key={virtualRow.key}
                          role="row"
                          className={clsx(
                            "absolute left-0 grid border-b border-ink/10 text-sm text-ink dark:border-white/10 dark:text-white",
                            absoluteRowIndex % 2 === 0
                              ? "bg-white dark:bg-[#13253e]"
                              : "bg-paper/70 dark:bg-[#1a304c]"
                          )}
                          style={{
                            height: `${virtualRow.size}px`,
                            transform: `translateY(${virtualRow.start}px)`,
                            width: "100%",
                            minWidth: totalWidth,
                            gridTemplateColumns
                          }}
                        >
                          {parsedCsv.headers.map((header, columnIndex) => {
                            const cellValue = row?.[columnIndex] ?? "";

                            return (
                            <div
                              key={`${header}-${columnIndex}`}
                              role="cell"
                              className="flex min-w-0 items-center border-r border-ink/10 px-3 dark:border-white/10"
                              title={cellValue}
                            >
                              <span className="truncate">{cellValue}</span>
                            </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <aside
            hidden={isExpanded}
            className={clsx(
              "rounded-lg border border-ink/10 bg-white shadow-soft dark:border-white/10 dark:bg-[#13253e]",
              isSummaryCollapsed ? "flex min-h-16 justify-center p-1.5" : "p-4"
            )}
          >
            {isSummaryCollapsed ? (
              <button
                type="button"
                onClick={() => setIsSummaryCollapsed(false)}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-ink/10 bg-paper text-ink transition hover:border-moss hover:text-moss dark:border-white/10 dark:bg-white/5 dark:text-white dark:hover:border-gold dark:hover:text-gold"
                aria-label="Expand dataset summary"
                title="Expand dataset summary"
              >
                <ChevronLeft aria-hidden="true" className="h-4 w-4" />
              </button>
            ) : (
              <>
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">
                    Dataset
                  </h2>
                  <button
                    type="button"
                    onClick={() => setIsSummaryCollapsed(true)}
                    className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-ink/10 bg-paper text-ink transition hover:border-coral hover:text-coral dark:border-white/10 dark:bg-white/5 dark:text-white dark:hover:border-gold dark:hover:text-gold"
                    aria-label="Collapse dataset summary"
                    title="Collapse dataset summary"
                  >
                    <ChevronRight aria-hidden="true" className="h-4 w-4" />
                  </button>
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-1">
                  <div className="rounded-md border border-ink/10 bg-paper p-3 dark:border-white/10 dark:bg-white/5">
                    <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-ink/50 dark:text-white/50">
                      Rows
                    </dt>
                    <dd className="mt-1 text-2xl font-semibold text-ink dark:text-white">
                      {parsedCsv?.rows.length.toLocaleString() ?? "0"}
                    </dd>
                  </div>
                  <div className="rounded-md border border-ink/10 bg-paper p-3 dark:border-white/10 dark:bg-white/5">
                    <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-ink/50 dark:text-white/50">
                      Columns
                    </dt>
                    <dd className="mt-1 text-2xl font-semibold text-ink dark:text-white">
                      {parsedCsv?.headers.length.toLocaleString() ?? "0"}
                    </dd>
                  </div>
                </dl>
                <div className="mt-4 rounded-md border border-ink/10 bg-paper p-3 dark:border-white/10 dark:bg-white/5">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ink/50 dark:text-white/50">
                    Processing
                  </p>
                  <p className="mt-2 text-sm leading-6 text-ink/70 dark:text-white/70">
                    CSV parsing runs locally in your browser in chunks. The table
                    renders visible rows only.
                  </p>
                </div>
              </>
            )}
          </aside>
        </div>
      </section>

      {pendingWorkbook && !parsedCsv && !errorMessage ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 px-4 backdrop-blur-sm dark:bg-black/55">
          <div role="dialog" aria-modal="true" aria-labelledby="sheet-title" className="csv-dialog w-full max-w-2xl rounded-lg border-2 border-gold bg-white p-6 text-center shadow-soft dark:bg-[#13253e]">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-lg bg-gold/20 text-ink dark:text-gold">
              <FileText aria-hidden="true" className="h-7 w-7" />
            </div>
            <p className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-coral">
              Excel workbook loaded
            </p>
            <h2 id="sheet-title" className="mt-2 text-2xl font-semibold text-ink dark:text-white">
              Select a sheet before viewing data
            </h2>
            <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-ink/70 dark:text-white/70">
              {pendingWorkbook.fileName} has{" "}
              {pendingWorkbook.sheetNames.length.toLocaleString()} sheet
              {pendingWorkbook.sheetNames.length === 1 ? "" : "s"}. The data
              table is waiting because this viewer displays one sheet at a time.
            </p>
            <p className="mt-4 text-sm font-semibold text-ink dark:text-white">
              Choose the sheet to display:
            </p>
            {sheetSelectionError ? (
              <div className="mt-4 rounded-md border border-coral/25 bg-coral/10 px-4 py-3 text-left text-sm font-semibold leading-6 text-coral dark:bg-coral/15">
                {sheetSelectionError}
              </div>
            ) : null}
            <button type="button" onClick={clearCsv} className="mt-4 rounded-md border border-ink/15 px-4 py-2 text-sm dark:text-white">Cancel</button>
            <div className="mt-4 grid max-h-[40vh] gap-2 overflow-auto sm:grid-cols-2">
              {pendingWorkbook.sheetNames.map((sheetName) => (
                <button
                  key={sheetName}
                  type="button"
                  onClick={() => loadExcelSheet(sheetName)}
                  className="min-h-12 truncate rounded-md border border-ink/10 bg-paper px-4 py-3 text-left text-sm font-semibold text-ink transition hover:border-moss hover:bg-moss hover:text-white dark:border-white/10 dark:bg-white/5 dark:text-white dark:hover:border-gold dark:hover:bg-gold dark:hover:text-ink"
                  title={sheetName}
                >
                  {sheetName}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
