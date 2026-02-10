/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        // Only scan backoffice templates - keep GOV.UK templates separate
        "./templates/backoffice/**/*.html",
    ],
    theme: {
        extend: {},
    },
    plugins: [],
};
