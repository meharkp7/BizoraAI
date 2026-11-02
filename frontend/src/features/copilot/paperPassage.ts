/** Locate a cited passage inside extracted paper text. */

const PAGE_MARKER = /\[Page (\d+)\]/g;
const CONTEXT_CHARS = 320;

export interface PassageMatch {
  /** The page the passage was taken from, when its marker was found. */
  page: number | null;
  pageFound: boolean;
  quoteFound: boolean;
  before: string;
  quote: string;
  after: string;
}

interface PageSlice {
  page: number;
  start: number;
  text: string;
}

/** Split marked-up text into per-page slices (marker line excluded). */
function splitPages(text: string): PageSlice[] {
  const markers: Array<{ page: number; index: number; end: number }> = [];
  PAGE_MARKER.lastIndex = 0;
  let match = PAGE_MARKER.exec(text);
  while (match !== null) {
    const lineEnd = text.indexOf("\n", match.index);
    markers.push({
      page: Number(match[1]),
      index: match.index,
      end: lineEnd === -1 ? text.length : lineEnd + 1,
    });
    match = PAGE_MARKER.exec(text);
  }
  if (markers.length === 0) return [];
  return markers.map((marker, i) => ({
    page: marker.page,
    start: marker.end,
    text: text.slice(marker.end, markers[i + 1]?.index ?? text.length),
  }));
}

function windowAround(scope: string, at: number, length: number): PassageMatch {
  const before = scope.slice(Math.max(0, at - CONTEXT_CHARS), at);
  const quote = scope.slice(at, at + length);
  const after = scope.slice(at + length, at + length + CONTEXT_CHARS);
  return { page: null, pageFound: false, quoteFound: true, before, quote, after };
}

/**
 * Find a cited quote inside paper text, preferring the cited page.
 * Falls back to the whole text when the page marker is missing, and to the
 * head of the scope when the quote itself is not found.
 */
export function findPassage(
  text: string,
  page: number | null,
  quote: string | null,
): PassageMatch {
  const pages = splitPages(text);
  const slice = page !== null ? pages.find((entry) => entry.page === page) : undefined;
  const scope = slice?.text ?? text;
  const pageFound = slice !== undefined;
  const resolvedPage = slice?.page ?? null;

  if (!quote) {
    return {
      page: resolvedPage,
      pageFound,
      quoteFound: false,
      before: "",
      quote: "",
      after: scope.slice(0, 2 * CONTEXT_CHARS),
    };
  }
  const exact = scope.indexOf(quote);
  if (exact !== -1) {
    return { ...windowAround(scope, exact, quote.length), page: resolvedPage, pageFound };
  }
  // Extraction whitespace rarely matches the citation exactly; retry on
  // progressively shorter leading runs before giving up on the match.
  for (const length of [80, 60, 40, 24]) {
    if (quote.length < length) continue;
    const headed = scope.indexOf(quote.slice(0, length));
    if (headed !== -1) {
      return {
        ...windowAround(scope, headed, Math.min(quote.length, scope.length - headed)),
        page: resolvedPage,
        pageFound,
      };
    }
  }
  return {
    page: resolvedPage,
    pageFound,
    quoteFound: false,
    before: "",
    quote: "",
    after: scope.slice(0, 2 * CONTEXT_CHARS),
  };
}
