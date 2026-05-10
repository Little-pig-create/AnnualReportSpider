from __future__ import annotations

APP_NAME = "AnnualReportSpider"
APP_TITLE = "Annual Report Spider Desktop"
APP_VERSION = "4.4.57"
APP_FILE_VERSION = "4.4.57.0"
PRODUCT_NAME = "AnnualReportSpider GUI"
COMPANY_NAME = "Little-pig-create"
COPYRIGHT = "Copyright (c) 2026 Little-pig-create"
GITHUB_URL = "https://github.com/Little-pig-create/AnnualReportSpider"
GITEE_URL = "https://gitee.com/xiaozhusir/AnnualReportSpider"
UPDATE_PRIMARY_CHANNEL = "github"
UPDATE_INSTALLER_MODE = "onedir"
UPDATE_PORTABLE_ASSET_NAME = "AnnualReportSpiderGUI.exe"
UPDATE_SOURCE_URLS = (
    "https://gitee.com/xiaozhusir/AnnualReportSpider/raw/codex/vuepywebview/update.json",
    "https://gitee.com/xiaozhusir/AnnualReportSpider/raw/main/update.json",
    "https://raw.githubusercontent.com/Little-pig-create/AnnualReportSpider/codex/vuepywebview/update.json",
    "https://raw.githubusercontent.com/Little-pig-create/AnnualReportSpider/main/update.json",
)
APP_ICON_DIRNAME = "assets"
APP_ICON_ICO_FILENAME = "annual_report_spider.ico"
APP_ICON_PNG_FILENAME = "annual_report_spider.png"


def build_installer_asset_name(version: str, mode: str = UPDATE_INSTALLER_MODE) -> str:
    return f"AnnualReportSpiderGUI-Setup-{version}-{mode}.exe"


def build_release_download_url(channel: str, version: str, asset_name: str) -> str:
    base_url = GITHUB_URL if channel == "github" else GITEE_URL
    return f"{base_url}/releases/download/{version}/{asset_name}"


def build_release_download_urls(version: str) -> dict[str, dict[str, str]]:
    installer_asset_name = build_installer_asset_name(version)
    return {
        "installer": {
            "fileName": installer_asset_name,
            "github": build_release_download_url("github", version, installer_asset_name),
            "gitee": build_release_download_url("gitee", version, installer_asset_name),
        },
        "portable": {
            "fileName": UPDATE_PORTABLE_ASSET_NAME,
            "github": build_release_download_url("github", version, UPDATE_PORTABLE_ASSET_NAME),
            "gitee": build_release_download_url("gitee", version, UPDATE_PORTABLE_ASSET_NAME),
        },
    }


def build_primary_download_url(version: str) -> str:
    return build_release_download_urls(version)["installer"][UPDATE_PRIMARY_CHANNEL]
