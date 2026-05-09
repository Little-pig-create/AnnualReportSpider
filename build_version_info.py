from __future__ import annotations

from pathlib import Path

from app_metadata import (
    APP_FILE_VERSION,
    APP_VERSION,
    COMPANY_NAME,
    COPYRIGHT,
    PRODUCT_NAME,
)


def version_tuple_text(version: str) -> str:
    version_numbers = [segment.strip() for segment in version.split(".") if segment.strip()]
    while len(version_numbers) < 4:
        version_numbers.append("0")
    return ", ".join(version_numbers[:4])


def main() -> None:
    project_root = Path(__file__).resolve().parent
    build_dir = project_root / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    output_path = build_dir / "version_info.txt"

    file_version_tuple = version_tuple_text(APP_FILE_VERSION)
    product_version_tuple = version_tuple_text(APP_VERSION)

    output_path.write_text(
        "\n".join(
            [
                "VSVersionInfo(",
                "  ffi=FixedFileInfo(",
                f"    filevers=({file_version_tuple}),",
                f"    prodvers=({product_version_tuple}),",
                "    mask=0x3f,",
                "    flags=0x0,",
                "    OS=0x40004,",
                "    fileType=0x1,",
                "    subtype=0x0,",
                "    date=(0, 0)",
                "  ),",
                "  kids=[",
                "    StringFileInfo(",
                "      [",
                "        StringTable(",
                "          '040904B0',",
                "          [",
                f"            StringStruct('CompanyName', '{COMPANY_NAME}'),",
                f"            StringStruct('FileDescription', '{PRODUCT_NAME}'),",
                f"            StringStruct('FileVersion', '{APP_FILE_VERSION}'),",
                f"            StringStruct('InternalName', '{PRODUCT_NAME}'),",
                f"            StringStruct('LegalCopyright', '{COPYRIGHT}'),",
                f"            StringStruct('OriginalFilename', 'AnnualReportSpiderGUI.exe'),",
                f"            StringStruct('ProductName', '{PRODUCT_NAME}'),",
                f"            StringStruct('ProductVersion', '{APP_VERSION}')",
                "          ]",
                "        )",
                "      ]",
                "    ),",
                "    VarFileInfo([VarStruct('Translation', [1033, 1200])])",
                "  ]",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(output_path)


if __name__ == "__main__":
    main()
