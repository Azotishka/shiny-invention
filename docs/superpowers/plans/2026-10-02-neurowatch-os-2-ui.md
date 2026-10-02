# NeuroWatch OS 2 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crowded NeuroWatch OS v0.8 screen layout with a deterministic, readable UI where each screen has non-overlapping regions and preserve the working USB/recovery path.

**Architecture:** Keep the existing single-file Watchy sketch and Preferences model to minimize firmware risk. Introduce centralized screen geometry constants and small drawing helpers, then migrate the watch face, menu, editors, status, steps, and about screens to those regions.

**Tech Stack:** Arduino C++, Watchy 1.4.7, ESP32-PICO-D4, GxEPD, Preferences, existing project configuration.

**Spec:** docs/superpowers/specs/2026-10-02-neurowatch-os-2-ui-design.md

## Global Constraints
- Preserve the existing USB recovery/install path and firmware target.
- Keep one standard built-in watch face.
- Do not allow text or widgets to overlap.
- Keep all important content inside the 200x200 display bounds.
- Keep existing button semantics and settings persistence unless explicitly improved by the UI work.
- Avoid adding runtime-heavy dependencies.

## Review Focus
- Long/large time and date values must remain inside their reserved regions.
- Battery voltage and percentage must not collide with the battery bar.
- Menu selection highlighting must not touch the footer or adjacent rows.
- Editor fields must remain separated when values reach their maximum widths.
- Status/about screens must keep the final row inside the display.

### Task 1: Add deterministic layout geometry

**Files:**
- Create: tests/test_neurowatch_layout.py
- Modify: firmware/NeuroWatch_OS/NeuroWatch_OS.ino

**Interfaces:**
- Produces centralized geometry constants used by all updated screens.

- [ ] Step 1: Write the failing geometry test covering 200x200 bounds and pairwise non-overlap of main-screen regions.
- [ ] Step 2: Run python tests/test_neurowatch_layout.py and verify it fails because the new geometry constants are absent.
- [ ] Step 3: Add NW_LAYOUT_* constants and region helpers to the sketch.
- [ ] Step 4: Run the test and verify it passes.
- [ ] Step 5: Commit as feat: add deterministic NeuroWatch UI layout.

### Task 2: Rebuild the standard watch face

**Files:**
- Modify: firmware/NeuroWatch_OS/NeuroWatch_OS.ino
- Test: tests/test_neurowatch_layout.py

**Interfaces:**
- Consumes Task 1 geometry.
- Produces a standard face with dedicated header, time, date, battery, steps, alarm, and controls regions.

- [ ] Step 1: Add failing source assertions for dedicated main-face regions and absence of legacy footer strings.
- [ ] Step 2: Run the test and verify the assertions fail.
- [ ] Step 3: Implement the new face using the centralized geometry and compact labels.
- [ ] Step 4: Run the test and verify it passes.
- [ ] Step 5: Commit as feat: rebuild readable standard watch face.

### Task 3: Make settings/editors/status screens collision-safe

**Files:**
- Modify: firmware/NeuroWatch_OS/NeuroWatch_OS.ino
- Test: tests/test_neurowatch_layout.py

**Interfaces:**
- Consumes Task 1 geometry.
- Keeps existing settings behavior while separating title, content, navigation, and timeout regions.

- [ ] Step 1: Add failing assertions for the reserved editor/footer/status regions.
- [ ] Step 2: Run the test and verify failure.
- [ ] Step 3: Update editor header/footer, date/time editor, step-goal editor, status, steps, reset, and about screens to use explicit non-overlapping regions.
- [ ] Step 4: Run the test and verify all assertions pass.
- [ ] Step 5: Commit as feat: prevent NeuroWatch screen element overlap.

### Task 4: Final static verification

**Files:**
- Modify: tests/test_neurowatch_layout.py

- [ ] Step 1: Run the complete Python UI-layout test suite.
- [ ] Step 2: Inspect the final sketch for USB/recovery-independent changes only.
- [ ] Step 3: Commit verification updates if needed.