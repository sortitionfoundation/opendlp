/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        // Only scan backoffice templates - keep GOV.UK templates separate
        "./templates/backoffice/**/*.html",
    ],
    // Class names built by string concat in Jinja macros never appear as
    // literals in scanned templates, so Tailwind's content-scanner purges
    // their @layer components rules. Safelist keeps them in the output.
    safelist: [
        "btn--primary",
        "btn--secondary",
        "btn--tertiary",
        "btn--danger",
        "btn--icon",
    ],
    theme: {
        extend: {},
    },
    plugins: [],
};
