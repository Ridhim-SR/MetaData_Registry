import { useIsFetching } from "@tanstack/react-query";

/**
 * Global loading indicator: a thin indeterminate bar pinned to the top of
 * the viewport, visible whenever ANY query is fetching. Rendered once in
 * RegistryLayout so every page gets it; section skeletons cover the content
 * areas while their own queries load.
 */
export function TopLoadingBar() {
  const fetching = useIsFetching();
  if (fetching === 0) return null;
  return (
    <div
      role="status"
      aria-label="Loading"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        height: 3,
        zIndex: 200,
        background: "var(--bg-alt)",
        overflow: "hidden",
      }}
    >
      <div className="top-loading-bar-fill" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
