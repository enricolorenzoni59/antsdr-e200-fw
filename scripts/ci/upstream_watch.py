#!/usr/bin/env python3
"""Compare the pinned E200 components with their upstream releases.

Runs weekly from .github/workflows/upstream-watch.yml. Dependabot covers
GitHub Actions and pip; this script covers the kernel, Buildroot, libiio,
libad9361, the Arm toolchain and the vendor BSP, which are pinned by lock
files and Buildroot recipes.

Only standard library modules plus the preinstalled `gh` CLI are used.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = os.environ.get("GITHUB_REPOSITORY", "enricolorenzoni59/antsdr-e200-fw")
ISSUE_TITLE = "Upstream dependency watch"
STATE_RE = re.compile(r"<!-- upstream-watch-state: ([0-9a-f]{64}) -->")

BR_PACKAGES = {
    "BusyBox": "package/busybox/busybox.mk",
    "Dropbear": "package/dropbear/dropbear.mk",
    "Python 3": "package/python3/python3.mk",
    "Bash": "package/bash/bash.mk",
    "iproute2": "package/iproute2/iproute2.mk",
    "ethtool": "package/ethtool/ethtool.mk",
    "iperf3": "package/iperf3/iperf3.mk",
    "zstd": "package/zstd/zstd.mk",
    "libxml2": "package/libxml2/libxml2.mk",
    "libffi": "package/libffi/libffi.mk",
    "ncurses": "package/ncurses/ncurses.mk",
    "readline": "package/readline/readline.mk",
}


def load_lock(name):
    return json.loads((ROOT / "configs" / name).read_text())


def gh_json(*args):
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out)


def http_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "e200-upstream-watch"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode()


def http_json(url):
    return json.loads(http_text(url))


def version_tuple(value):
    """Turn 6.12.115, v1.0.0, 2026.08.1 or 14.2.rel1 into comparable ints."""
    return tuple(int(part) for part in re.findall(r"\d+", value))


def is_newer(candidate, current):
    try:
        return version_tuple(candidate) > version_tuple(current)
    except (TypeError, ValueError):
        return candidate != current


def buildroot_stable_tags():
    tags = gh_json("api", "repos/buildroot/buildroot/tags?per_page=100")
    names = [tag["name"] for tag in tags
             if re.fullmatch(r"\d{4}\.\d{2}(\.\d+)?", tag["name"])]
    return sorted(names, key=version_tuple)


def buildroot_mk(tag, path):
    return http_text(f"https://raw.githubusercontent.com/buildroot/buildroot/{tag}/{path}")


def mk_versions(text):
    values = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Z0-9_]+)\s*=\s*(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def mk_version(text, package):
    values = mk_versions(text)
    if package == "ncurses":
        major = values.get("NCURSES_VERSION_MAJOR", "")
        date = values.get("NCURSES_SNAPSHOT_DATE", "")
        return f"{major}-{date}" if major and date else major
    for key in (f"{package.upper().replace(' ', '').replace('-', '_')}_VERSION",
                *[name for name in values if name.endswith("_VERSION")]):
        if key not in values:
            continue
        value = values[key]
        for _ in range(3):
            value = re.sub(r"\$\(([A-Z0-9_]+)\)",
                           lambda match: values.get(match.group(1), match.group(0)),
                           value)
        if "$(" not in value:
            return value
    return "?"


def package_versions(tag):
    result = {}
    for package, path in BR_PACKAGES.items():
        try:
            result[package] = mk_version(buildroot_mk(tag, path), package)
        except Exception as error:  # a single package failure must not hide the rest
            result[package] = f"error: {error}"
    return result


def kernel_latest(series):
    releases = http_json("https://www.kernel.org/releases.json")["releases"]
    matches = [item["version"] for item in releases
               if item["version"].startswith(f"{series}.")]
    return sorted(matches, key=version_tuple)[-1]


def kernel_latest_lts():
    releases = http_json("https://www.kernel.org/releases.json")["releases"]
    matches = [item["version"] for item in releases if item["moniker"] == "longterm"]
    return sorted(matches, key=version_tuple)[-1]


def latest_release(repo):
    try:
        return gh_json("api", f"repos/{repo}/releases/latest")["tag_name"]
    except subprocess.CalledProcessError:
        return None


def latest_versioned_release(repo):
    releases = gh_json("api", f"repos/{repo}/releases?per_page=100")
    tags = [release["tag_name"] for release in releases
            if re.fullmatch(r"v\d+\.\d+", release["tag_name"])]
    return sorted(tags, key=version_tuple)[-1] if tags else None


def main_commit(repo):
    return gh_json("api", f"repos/{repo}/commits/main")


def toolchain_version(buildroot_ref):
    text = buildroot_mk(
        buildroot_ref,
        "toolchain/toolchain-external/toolchain-external-arm-arm/"
        "toolchain-external-arm-arm.mk",
    )
    values = mk_versions(text)
    return values.get("TOOLCHAIN_EXTERNAL_ARM_ARM_VERSION", "?")


def row(component, current, latest, note, actionable=True, changed=None):
    if changed is None:
        changed = is_newer(latest, current) if actionable else False
    return {
        "component": component,
        "current": current,
        "latest": latest,
        "note": note,
        "changed": changed,
    }


def collect():
    modernization = load_lock("modernization.lock.json")
    release = load_lock("release.lock.json")
    vendor = load_lock("vendor-v039-artifacts.json")

    current_br = modernization["buildroot"]["tag"]
    stable_tags = buildroot_stable_tags()
    latest_br = stable_tags[-1] if stable_tags else current_br

    current_kernel = modernization["kernel"]["stable_target"]
    kernel_series = ".".join(current_kernel.split(".")[:2])
    latest_kernel = kernel_latest(kernel_series)
    latest_lts = kernel_latest_lts()

    current_libiio = modernization["libiio"]["tag"]
    libiio_latest = latest_release("analogdevicesinc/libiio") or current_libiio

    ad9361 = modernization["libad9361"]["commit"]
    ad9361_head = main_commit("analogdevicesinc/libad9361-iio")

    current_vendor = vendor["release"]
    vendor_latest = latest_versioned_release("MicroPhase/antsdr-fw-patch") or current_vendor

    current_toolchain = release["userspace"]["compiler"].replace("Arm GNU ", "")
    latest_toolchain = toolchain_version("master")

    pinned = [
        row("Linux " + kernel_series + ".y", current_kernel, latest_kernel,
            "Stable patch series; low risk."),
        row("Kernel latest LTS", current_kernel, latest_lts,
            "Major migration; requires an ADI/E200 port and qualification.", actionable=False),
        row("Buildroot", current_br, latest_br,
            f"Stable patch release. master is the next feature release; "
            f"it currently carries the package versions in the second table."),
        row("Userspace toolchain", current_toolchain, latest_toolchain,
            "Buildroot supports the newer Arm GNU toolchain; select it with "
            "E200_USERSPACE_TOOLCHAIN=15.2 and run the full runtime tests."),
        row("libiio", current_libiio, libiio_latest,
            "Native v1 runtime; keep the release tag pinned."),
        row("libad9361-iio", ad9361[:12], ad9361_head["sha"][:12],
            "Pinned to upstream main; review new commits before moving.",
            changed=ad9361 != ad9361_head["sha"]),
        row("Vendor BSP", current_vendor, vendor_latest,
            "Latest versioned MicroPhase BSP. The antsdr_mesh release is a "
            "different firmware line, not a drop-in upgrade.", actionable=False),
        row("Kernel compiler", "GCC 15.2.0", "GCC 15.3.0",
            "Tied to the pinned Ubuntu 26.04 snapshot; no direct update.", actionable=False),
    ]

    current_pkgs = package_versions(current_br)
    stable_pkgs = package_versions(latest_br)
    master_pkgs = package_versions("master")

    packages = []
    for package in BR_PACKAGES:
        current = current_pkgs[package]
        stable = stable_pkgs[package]
        master = master_pkgs[package]
        latest = master if master not in ("?", "error") else stable
        changed = (is_newer(stable, current) if stable not in ("?",) else False) or \
                  (is_newer(master, current) if master not in ("?",) else False)
        packages.append({
            "package": package,
            "current": current,
            "stable": stable,
            "master": master,
            "changed": changed,
        })

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "current_br": current_br,
        "latest_br": latest_br,
        "pinned": pinned,
        "packages": packages,
    }


def render(data):
    lines = [
        f"<!-- upstream-watch-state: {state_hash(data)} -->",
        "",
        "# Upstream dependency watch",
        "",
        f"Generated: {data['generated']}",
        "",
        "## Pinned components",
        "",
        "| Component | Current | Latest | Note |",
        "| --- | --- | --- | --- |",
    ]
    for item in data["pinned"]:
        if item["changed"]:
            mark = "**update**"
        elif is_newer(item["latest"], item["current"]):
            mark = "newer, not actionable"
        else:
            mark = "current"
        lines.append(
            f"| {item['component']} | `{item['current']}` | `{item['latest']}` "
            f"({mark}) | {item['note']} |"
        )

    lines += [
        "",
        f"## Buildroot packages ({data['current_br']} → {data['latest_br']} / master)",
        "",
        "| Package | " + data["current_br"] + " | " + data["latest_br"] + " | master |",
        "| --- | --- | --- | --- |",
    ]
    for item in data["packages"]:
        lines.append(
            f"| {item['package']} | `{item['current']}` | `{item['stable']}` "
            f"| `{item['master']}` |"
        )

    changes = [item for item in data["pinned"] if item["changed"]]
    changes += [item for item in data["packages"] if item["changed"]]
    lines += ["", "## Actionable updates", ""]
    if changes:
        for item in changes:
            if "component" in item:
                lines.append(
                    f"- **{item['component']}**: `{item['current']}` → `{item['latest']}`"
                )
            else:
                latest = item["master"] if item["master"] not in ("?", "error") else item["stable"]
                lines.append(
                    f"- **{item['package']}**: `{item['current']}` → `{latest}`"
                )
    else:
        lines.append("- None: every tracked component is current.")
    lines.append("")
    lines.append(
        "Dependabot separately covers GitHub Actions and `requirements-test.txt`."
    )
    return "\n".join(lines)


def state_hash(data):
    changes = []
    for item in data["pinned"]:
        if item["changed"]:
            changes.append([item["component"], item["current"], item["latest"]])
    for item in data["packages"]:
        if item["changed"]:
            changes.append([item["package"], item["current"], item["stable"], item["master"]])
    return hashlib.sha256(json.dumps(changes, sort_keys=True).encode()).hexdigest()


def find_issue():
    issues = gh_json("api", f"repos/{REPO}/issues?state=open&per_page=100")
    for issue in issues:
        if "pull_request" not in issue and issue["title"] == ISSUE_TITLE:
            return issue
    return None


def main():
    data = collect()
    body = render(data)
    changes = state_hash(data)
    issue = find_issue()

    if os.environ.get("UPSTREAM_WATCH_DRY_RUN") == "1":
        print(body)
        return 0

    summary = Path(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull))
    with summary.open("w") as handle:
        handle.write(body + "\n")

    updates = any(item["changed"] for item in data["pinned"]) or \
        any(item["changed"] for item in data["packages"])

    if issue:
        previous = STATE_RE.search(issue.get("body") or "")
        previous_hash = previous.group(1) if previous else None
        if changes == previous_hash:
            print("No change since the last run; leaving the issue untouched.")
            return 0
        subprocess.run(
            ["gh", "api", "-X", "PATCH", f"repos/{REPO}/issues/{issue['number']}",
             "--input", "-"],
            input=json.dumps({"body": body}), text=True, check=True,
        )
        if updates:
            subprocess.run(
                ["gh", "issue", "comment", str(issue["number"]), "--repo", REPO,
                 "--body", "Weekly check: upstream updates are available (see the issue body)."],
                check=True,
            )
            print("Updated issue with new updates.")
        else:
            subprocess.run(
                ["gh", "issue", "close", str(issue["number"]), "--repo", REPO,
                 "--comment", "All tracked components are current."],
                check=True,
            )
            print("Closed issue: everything is current.")
    elif updates:
        subprocess.run(
            ["gh", "issue", "create", "--repo", REPO, "--title", ISSUE_TITLE,
             "--body-file", "-"], input=body, text=True, check=True,
        )
        print("Created issue with upstream updates.")
    else:
        print("No updates; no issue created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
