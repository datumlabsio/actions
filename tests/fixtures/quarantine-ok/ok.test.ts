// Annotation on the line above is within the window.
// quarantined(@humayun-1, 2099-01-01): timing-dependent in CI
it.skip("renders the empty state", () => {});

// runIf is conditional — exempt, no annotation needed.
it.runIf(process.platform === "linux")("uses inotify", () => {});
