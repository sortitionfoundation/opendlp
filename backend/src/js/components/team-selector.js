// ABOUTME: Alpine component for conditional team fields in Google Sheets forms
// ABOUTME: Tracks which team is selected so dependent fields can show or hide

/**
 * Build the teamSelector component state.
 *
 * @param {string} initialTeam - the team selected when the page rendered
 * @returns {Object} Alpine component state
 */
export function teamSelector(initialTeam) {
  return {
    selectedTeam: initialTeam || "other",
  };
}
