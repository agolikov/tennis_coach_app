/**
 * Returns auth headers for API requests.
 *
 * No external identity provider is configured, so requests carry no
 * Authorization header. Kept as a seam so adding one later touches one file.
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  return {};
}
