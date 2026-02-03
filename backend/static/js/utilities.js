// ABOUTME: JavaScript utilities for form confirmations, clipboard, downloads, and print
// ABOUTME: Provides event-driven handlers for common UI interactions without inline handlers

// Handle button clicks for confirmations and print
document.addEventListener("click", function (e) {
    // Check for confirmation
    const confirmMsg = e.target.dataset.confirm;
    if (confirmMsg && !confirm(confirmMsg)) {
        e.preventDefault();
        return;
    }

    // Check for print
    if (e.target.dataset.print !== undefined) {
        window.print();
    }
});

// Copy text to clipboard with fallback for older browsers
async function copyToClipboard(elementId, successMessage) {
    const element = document.getElementById(elementId);
    const text = element.textContent || element.value;

    try {
        await navigator.clipboard.writeText(text);
        alert(successMessage);
    } catch (err) {
        // Fallback for older browsers
        fallbackCopyToClipboard(text, successMessage);
    }
}

function fallbackCopyToClipboard(text, successMessage) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();

    try {
        document.execCommand("copy");
        alert(successMessage);
    } catch (err) {
        alert("Failed to copy to clipboard");
    }

    document.body.removeChild(textarea);
}

// Download 2FA backup codes as text file
function downloadBackupCodes() {
    const codesElement = document.getElementById("backup-codes");
    const codes = Array.from(codesElement.children)
        .map((el) => el.textContent)
        .join("\n");
    const blob = new Blob([codes], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "2fa-backup-codes.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
