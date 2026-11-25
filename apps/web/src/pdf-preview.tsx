import { appPath } from "./paths";
import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Dialog } from "./ui";
import { type Artifact, type Project } from "./types";
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
export function PDFPreview({
  project,
  artifact,
  onClose,
}: {
  project: Project;
  artifact: Artifact;
  onClose: () => void;
}) {
  return (
    <Dialog
      title="Generated review PDF"
      subtitle={`Revision ${artifact.revision} · ${project.title}. Edit points and notes in Drawing workspace.`}
      onClose={onClose}
      wide
    >
      <PDFPages
        url={appPath(
          `api/v1/projects/${project.id}/artifacts/${artifact.id}/pdf`,
        )}
        totalAdditions={artifact.count}
      />
    </Dialog>
  );
}

export function PDFPages({
  url,
  totalAdditions,
  onPageRendered,
}: {
  url: string;
  totalAdditions?: number;
  onPageRendered?: (page: number, totalPages: number) => void;
}) {
  const [doc, setDoc] = useState<pdfjs.PDFDocumentProxy | null>(null),
    [pageIndex, setPageIndex] = useState(1),
    [width, setWidth] = useState(700),
    [zoom, setZoom] = useState(1),
    [count, setCount] = useState(0),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const canvas = useRef<HTMLCanvasElement>(null),
    container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    let task: pdfjs.PDFDocumentLoadingTask | undefined;
    setDoc(null);
    setPageIndex(1);
    setZoom(1);
    setError("");
    setLoading(true);
    setCount(0);
    fetch(url, {
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok)
          throw new Error(
            `Review PDF request failed (HTTP ${response.status}).`,
          );
        return response.arrayBuffer();
      })
      .then((bytes) => {
        if (!alive) return;
        task = pdfjs.getDocument({
          data: new Uint8Array(bytes),
          isEvalSupported: false,
        });
        return task.promise;
      })
      .then((value) => {
        if (alive && value) setDoc(value);
      })
      .catch((e) => {
        if (alive) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      alive = false;
      controller.abort();
      void task?.destroy().catch(() => undefined);
    };
  }, [url]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(220, entries[0].contentRect.width - 4)),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!doc || !canvas.current) return;
    let alive = true,
      task: pdfjs.RenderTask | undefined;
    setLoading(true);
    doc
      .getPage(pageIndex)
      .then(async (page) => {
        if (!alive) return;
        const base = page.getViewport({ scale: 1 }),
          scale = (width / base.width) * zoom,
          ratio = Math.min(window.devicePixelRatio || 1, 2),
          viewport = page.getViewport({ scale: scale * ratio });
        const c = canvas.current!;
        c.width = viewport.width;
        c.height = viewport.height;
        c.style.width = `${width * zoom}px`;
        c.style.height = `${base.height * scale}px`;
        task = page.render({
          canvasContext: c.getContext("2d")!,
          viewport,
          annotationMode: pdfjs.AnnotationMode.ENABLE,
        });
        await task.promise;
        const annotations = await page.getAnnotations({ intent: "display" });
        if (alive) {
          setCount(annotations.length);
          setLoading(false);
          onPageRendered?.(pageIndex, doc.numPages);
        }
      })
      .catch((e) => {
        if (alive && e.name !== "RenderingCancelledException") {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      alive = false;
      task?.cancel();
    };
  }, [doc, pageIndex, width, zoom]);
  return (
    <>
      <div
        className="pdf-preview"
        ref={container}
        style={{
          overflow: "auto",
          background: "#edf1f7",
          border: "1px solid #dfe6f1",
          borderRadius: 8,
          padding: 2,
          minHeight: 150,
          maxHeight: "65vh",
        }}
      >
        {loading && (
          <p
            className="fine-print"
            style={{
              padding: 15,
              display: "flex",
              gap: 8,
              alignItems: "center",
            }}
          >
            <Loader2 className="spin" size={15} />
            Rendering the generated PDF…
          </p>
        )}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <canvas
          ref={canvas}
          aria-label="Generated PDF page"
          style={{ display: loading ? "none" : "block", background: "white" }}
        />
      </div>
      <div
        className="inline-actions"
        style={{ justifyContent: "space-between", marginTop: 16 }}
      >
        <span className="fine-print">
          {count} native annotations on this page
          {totalAdditions == null ? "" : ` · ${totalAdditions} total additions`}
        </span>
        <div className="inline-actions">
          <button
            className="icon-button"
            aria-label="Zoom out native PDF"
            disabled={loading || zoom <= 1}
            onClick={() => setZoom((value) => Math.max(1, value - 0.5))}
          >
            <ZoomOut size={16} />
          </button>
          <button
            className="button secondary"
            onClick={() => setZoom(1)}
            disabled={loading || zoom === 1}
            aria-label="Fit native PDF width"
          >
            {zoom === 1 ? "Fit width" : `${Math.round(zoom * 100)}%`}
          </button>
          <button
            className="icon-button"
            aria-label="Zoom in native PDF"
            disabled={loading || zoom >= 4}
            onClick={() => setZoom((value) => Math.min(4, value + 0.5))}
          >
            <ZoomIn size={16} />
          </button>
          <button
            className="icon-button"
            aria-label="Previous preview page"
            disabled={pageIndex === 1 || loading}
            onClick={() => setPageIndex((v) => v - 1)}
          >
            <ChevronLeft size={16} />
          </button>
          <span className="fine-print">
            {pageIndex} / {doc?.numPages || "—"}
          </span>
          <button
            className="icon-button"
            aria-label="Next preview page"
            disabled={!doc || pageIndex >= doc.numPages || loading}
            onClick={() => setPageIndex((v) => v + 1)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </>
  );
}
