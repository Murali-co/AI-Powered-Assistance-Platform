/**
 * URL Security Utilities (M15)
 * Sanitizes and validates external links to prevent XSS (e.g. javascript:, data: URIs)
 * and tabnabbing attacks.
 */

/**
 * Validates whether a URL is a safe external web link.
 * Permits only http: and https: schemes.
 *
 * @param {string} url - The candidate URL to validate
 * @returns {string|null} - The validated URL string, or null if invalid/unsafe
 */
export const getSafeExternalUrl = (url) => {
  if (!url || typeof url !== 'string') return null;
  const trimmed = url.trim();
  if (!trimmed) return null;

  try {
    // Parse using the standard WHATWG URL parser
    const parsed = new URL(trimmed);
    const protocol = parsed.protocol.toLowerCase();

    // Whitelist only safe web protocols
    if (protocol === 'http:' || protocol === 'https:') {
      return parsed.href;
    }

    // Explicitly reject unsafe schemes (javascript:, data:, vbscript:, etc.)
    return null;
  } catch {
    // If URL parsing fails (e.g. relative or malformed URL)
    return null;
  }
};

/**
 * Standard safe props for external links to prevent reverse tabnabbing (M15)
 */
export const SAFE_EXTERNAL_LINK_PROPS = {
  target: '_blank',
  rel: 'noopener noreferrer'
};
