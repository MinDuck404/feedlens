/** Backend timestamps without an offset are UTC, including SQLite timestamps. */
export function parseTimestamp(iso: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

export function groupName(url: string): string {
  const slug = (url.replace(/\/$/, "").split(/groups\/|\/r\/|x\.com\//).pop() ?? url).split(/[/?#]/)[0];
  let decoded = slug;
  try { decoded = decodeURIComponent(slug); } catch { /* A malformed saved URL must still render. */ }
  return decoded.replace(/[-_.]+/g, " ").trim() || url;
}

export const isRemoteText = (text: string): boolean => /remote|từ xa|wfh|work from home|远程|遠程|居家办公|居家辦公|在宅/i.test(text);

/** Serialize writes across form mounts; a rejected save must not block later saves. */
export function serialWriter<T>(write: (value: T) => Promise<unknown>) {
  let tail: Promise<unknown> = Promise.resolve();
  return (value: T) => {
    const next = tail.catch(() => {}).then(() => write(value));
    tail = next;
    return next;
  };
}


export function matchesJobType(type: string | null | undefined, filter: string): boolean {
  return filter === "all" || (type ?? "none") === filter;
}
