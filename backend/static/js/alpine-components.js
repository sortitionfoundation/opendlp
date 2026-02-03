// ABOUTME: Reusable Alpine.js components for OpenDLP
// ABOUTME: Provides data factories for conditional form fields and other interactive UI

// Alpine.js component for conditional team fields in Google Sheets forms
document.addEventListener("alpine:init", () => {
    Alpine.data("teamSelector", (initialTeam) => ({
        selectedTeam: initialTeam || "other",
    }));
});
