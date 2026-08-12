// ABOUTME: Unit tests for the patterns page file upload demo component
// ABOUTME: Covers size formatting, extension validation and the truncated text preview

import { describe, expect, it, vi } from "vitest";

import { fileUploadDemo, formatFileSize } from "./file-upload-demo.js";

function selectEvent(file) {
  return { target: { files: file ? [file] : [], value: "chosen.csv" } };
}

function csvFile(name, contents) {
  return new File([contents], name, { type: "text/csv" });
}

describe("formatFileSize", () => {
  it("reports small files in bytes", () => {
    expect(formatFileSize(512)).toBe("512 bytes");
  });

  it("switches to KB at 1024 bytes", () => {
    expect(formatFileSize(1023)).toBe("1023 bytes");
    expect(formatFileSize(1024)).toBe("1.0 KB");
  });

  it("switches to MB at a megabyte", () => {
    expect(formatFileSize(1024 * 1024 - 1)).toBe("1024.0 KB");
    expect(formatFileSize(1024 * 1024)).toBe("1.0 MB");
  });

  it("reports one decimal place", () => {
    expect(formatFileSize(1536)).toBe("1.5 KB");
  });
});

describe("fileUploadDemo initial state", () => {
  it("starts with nothing selected", () => {
    const state = fileUploadDemo();
    expect(state.fileName).toBe("");
    expect(state.fileSize).toBe("");
    expect(state.preview).toBe("");
    expect(state.error).toBe("");
  });
});

describe("fileUploadDemo onFileSelect", () => {
  it("clears everything when the selection is cancelled", () => {
    const state = fileUploadDemo();
    state.fileName = "old.csv";
    state.fileSize = "1.0 KB";

    state.onFileSelect(selectEvent(null));

    expect(state.fileName).toBe("");
    expect(state.fileSize).toBe("");
    expect(state.error).toBe("");
  });

  it("rejects a file that is not a CSV and resets the input", () => {
    const state = fileUploadDemo();
    const event = selectEvent(csvFile("notes.txt", "hello"));

    state.onFileSelect(event);

    expect(state.error).toBe("Please select a CSV file");
    expect(state.fileName).toBe("");
    expect(state.fileSize).toBe("");
    expect(event.target.value).toBe("");
  });

  it("records the name and formatted size of an accepted CSV", () => {
    const state = fileUploadDemo();

    state.onFileSelect(selectEvent(csvFile("people.csv", "a".repeat(2048))));

    expect(state.error).toBe("");
    expect(state.fileName).toBe("people.csv");
    expect(state.fileSize).toBe("2.0 KB");
  });

  it("clears a previous error when a valid file follows an invalid one", () => {
    const state = fileUploadDemo();
    state.onFileSelect(selectEvent(csvFile("notes.txt", "hello")));
    expect(state.error).not.toBe("");

    state.onFileSelect(selectEvent(csvFile("people.csv", "name,age")));

    expect(state.error).toBe("");
  });

  it("previews a short file in full", async () => {
    const state = fileUploadDemo();
    state.onFileSelect(selectEvent(csvFile("people.csv", "name,age\nAda,36")));

    await vi.waitFor(() => expect(state.preview).not.toBe(""));
    expect(state.preview).toBe("name,age\nAda,36");
  });

  it("truncates a long file to 200 characters with an ellipsis", async () => {
    const state = fileUploadDemo();
    state.onFileSelect(selectEvent(csvFile("big.csv", "x".repeat(500))));

    await vi.waitFor(() => expect(state.preview).not.toBe(""));
    expect(state.preview).toBe("x".repeat(200) + "...");
  });
});
