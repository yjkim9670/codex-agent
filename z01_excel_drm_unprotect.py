#!/usr/bin/env python3
"""Re-save staged Office files through Office COM to remove DRM wrappers."""

from __future__ import annotations

import argparse
import gc
import os
import sys
from pathlib import Path
from typing import List

EXCEL_EXTENSIONS = {".xls", ".xlsx", ".xlsm"}
POWERPOINT_EXTENSIONS = {".ppt", ".pptx", ".pptm"}
OFFICE_DRM_EXTENSIONS = EXCEL_EXTENSIONS | POWERPOINT_EXTENSIONS

EXCEL_FILE_FORMAT_BY_EXT = {
    ".xls": 56,   # xlExcel8
    ".xlsx": 51,  # xlOpenXMLWorkbook
    ".xlsm": 52,  # xlOpenXMLWorkbookMacroEnabled
}
POWERPOINT_FILE_FORMAT_BY_EXT = {
    ".ppt": 1,    # ppSaveAsPresentation
    ".pptx": 24,  # ppSaveAsOpenXMLPresentation
    ".pptm": 25,  # ppSaveAsOpenXMLPresentationMacroEnabled
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-save staged Office files by opening and saving with Office COM.",
    )
    parser.add_argument(
        "--stage-dir",
        required=True,
        help="Path to the staging directory.",
    )
    return parser.parse_args()


def collect_office_files(stage_dir: Path) -> List[Path]:
    results: List[Path] = []
    for root, dir_names, file_names in os.walk(stage_dir):
        dir_names.sort(key=str.lower)

        for file_name in sorted(file_names):
            file_path = Path(root) / file_name
            if file_path.suffix.lower() in OFFICE_DRM_EXTENSIONS:
                results.append(file_path)

    results.sort(key=lambda item: str(item).lower())
    return results


def remove_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def resave_excel_file(excel_app, source_path: Path) -> None:
    suffix = source_path.suffix.lower()
    file_format = EXCEL_FILE_FORMAT_BY_EXT.get(suffix)
    if file_format is None:
        raise RuntimeError(
            f"Unsupported Excel extension for DRM re-save: {source_path}"
        )

    temp_output = source_path.with_name(
        f"{source_path.stem}.__drm_unlocked__.tmp{suffix}"
    )

    workbook = None
    try:
        remove_if_exists(temp_output)
        workbook = excel_app.Workbooks.Open(
            str(source_path),
            UpdateLinks=0,
            ReadOnly=False,
            IgnoreReadOnlyRecommended=True,
            AddToMru=False,
            Notify=False,
        )
        workbook.SaveAs(
            str(temp_output),
            FileFormat=file_format,
            ConflictResolution=2,
            AddToMru=False,
            Local=True,
        )
    except Exception:
        remove_if_exists(temp_output)
        raise
    finally:
        if workbook is not None:
            workbook.Close(SaveChanges=False)
        workbook = None
        gc.collect()

    if not temp_output.is_file():
        raise RuntimeError(f"SaveAs output not found: {temp_output}")

    os.replace(str(temp_output), str(source_path))


def resave_powerpoint_file(powerpoint_app, source_path: Path) -> None:
    suffix = source_path.suffix.lower()
    file_format = POWERPOINT_FILE_FORMAT_BY_EXT.get(suffix)
    if file_format is None:
        raise RuntimeError(
            f"Unsupported PowerPoint extension for DRM re-save: {source_path}"
        )

    temp_output = source_path.with_name(
        f"{source_path.stem}.__drm_unlocked__.tmp{suffix}"
    )

    presentation = None
    try:
        remove_if_exists(temp_output)
        presentation = powerpoint_app.Presentations.Open(
            str(source_path),
            ReadOnly=False,
            Untitled=False,
            WithWindow=False,
        )
        presentation.SaveAs(str(temp_output), file_format)
    except Exception:
        remove_if_exists(temp_output)
        raise
    finally:
        if presentation is not None:
            presentation.Close()
        presentation = None
        gc.collect()

    if not temp_output.is_file():
        raise RuntimeError(f"SaveAs output not found: {temp_output}")

    os.replace(str(temp_output), str(source_path))


def unlock_one_file(excel_app, source_path: Path) -> None:
    """Backward-compatible wrapper for the historical Excel-only helper name."""
    resave_excel_file(excel_app, source_path)


def main() -> int:
    args = parse_args()
    stage_dir = Path(args.stage_dir).expanduser().resolve()

    if not stage_dir.is_dir():
        print(f"[ERROR] Stage directory not found: {stage_dir}", file=sys.stderr)
        return 2

    if os.name != "nt":
        print(
            "[ERROR] Office DRM re-save requires Windows + installed Office (win32com).",
            file=sys.stderr,
        )
        return 2

    try:
        import pythoncom  # type: ignore
        import win32com.client as win32  # type: ignore
    except Exception as exc:
        print(
            f"[ERROR] pywin32 modules (pythoncom/win32com) are required: {exc}",
            file=sys.stderr,
        )
        return 2

    office_files = collect_office_files(stage_dir)
    if not office_files:
        print("[INFO] No Office DRM target files found in staging.")
        return 0

    excel_files = [
        file_path
        for file_path in office_files
        if file_path.suffix.lower() in EXCEL_EXTENSIONS
    ]
    powerpoint_files = [
        file_path
        for file_path in office_files
        if file_path.suffix.lower() in POWERPOINT_EXTENSIONS
    ]

    print(f"[INFO] Office DRM re-save target count: {len(office_files)}")
    if excel_files:
        print(f"[INFO] Excel target count: {len(excel_files)}")
    if powerpoint_files:
        print(f"[INFO] PowerPoint target count: {len(powerpoint_files)}")

    com_initialized = False
    excel_app = None
    powerpoint_app = None
    try:
        pythoncom.CoInitialize()
        com_initialized = True

        if excel_files:
            excel_app = win32.DispatchEx("Excel.Application")
            excel_app.Visible = False
            excel_app.DisplayAlerts = False

            try:
                excel_app.AskToUpdateLinks = False
            except Exception:
                pass

            try:
                excel_app.EnableEvents = False
            except Exception:
                pass

            for index, file_path in enumerate(excel_files, start=1):
                print(
                    f"[INFO] [{index}/{len(excel_files)}] "
                    f"Re-saving Excel: {file_path}"
                )
                try:
                    resave_excel_file(excel_app, file_path)
                except Exception as exc:
                    print(
                        f"[ERROR] Failed to re-save Excel file '{file_path}': {exc}",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    f"[INFO] [{index}/{len(excel_files)}] "
                    f"Re-saved Excel: {file_path}"
                )

        if powerpoint_files:
            powerpoint_app = win32.DispatchEx("PowerPoint.Application")

            try:
                powerpoint_app.DisplayAlerts = 1  # ppAlertsNone
            except Exception:
                pass

            for index, file_path in enumerate(powerpoint_files, start=1):
                print(
                    f"[INFO] [{index}/{len(powerpoint_files)}] "
                    f"Re-saving PowerPoint: {file_path}"
                )
                try:
                    resave_powerpoint_file(powerpoint_app, file_path)
                except Exception as exc:
                    print(
                        f"[ERROR] Failed to re-save PowerPoint file '{file_path}': {exc}",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    f"[INFO] [{index}/{len(powerpoint_files)}] "
                    f"Re-saved PowerPoint: {file_path}"
                )

    finally:
        if powerpoint_app is not None:
            try:
                powerpoint_app.Quit()
            except Exception:
                pass
        powerpoint_app = None

        if excel_app is not None:
            try:
                excel_app.Quit()
            except Exception:
                pass
        excel_app = None
        gc.collect()

        if com_initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    print("[INFO] Office DRM re-save completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
