/** Display helper: show DB values with a capital first letter.
 * Data stays untouched (links, FQNs, API params still use raw values);
 * only rendered labels go through this.
 */
export function capitalizeFirst(value: string | null | undefined): string {
  if (!value) return "";
  return value.charAt(0).toUpperCase() + value.slice(1);
}
