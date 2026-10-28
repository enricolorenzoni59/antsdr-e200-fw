# Prepare an SD release draft

The manual **Prepare SD release draft** workflow builds the dispatch commit,
collects its software sources/notices and uploads a prerelease **draft**.
It never publishes the draft or marks it Latest. Drafts are visible to repository
writers; firmware/source binaries are not uploaded as public Actions artifacts.
The existing complete-build workflow remains available for diagnostics only.

## Runner and invocation

After this workflow and its native-IIO dependencies are merged into the default
branch, register a dedicated non-root Linux x86-64 runner with labels
`self-hosted`, `linux`, `x64`, `e200-build`. Provide Docker access without an
interactive password, Python 3.11+, Git, GitHub CLI, 8 GiB RAM and at least
80 GiB free disk including space for the source bundle. Runner registration is
administration outside this PR; a job stays queued if no matching runner exists.
Both manual build workflows share a concurrency group to avoid replacing their
shared Docker image tags during another build.

Select the default branch in Actions, choose **Run workflow**, and enter a new
preview tag such as `v0.1.0-rc1`. The immutable `GITHUB_SHA` of that dispatch is
checked out explicitly and recorded in the source inventory and release manifest.
Existing tags/releases are refused, including existing drafts; choose a new tag
for a retry. Build and asset paths include the run ID and attempt and must be fresh.

The workflow checks the default-branch restriction before building and again
before upload. GitHub's release API can reject `GITHUB_TOKEN` if the target
commit's workflow files differ from the current default branch; if those files
change during a build, this run stops rather than pointing the release at a
different commit. See the [release API](https://docs.github.com/en/rest/releases/releases#create-a-release).
Only the draft job has `contents: write`; its token is passed to the release
steps, not to compilation or source collection, and checkout does not persist credentials.

## Assets and checks

The draft contains `e200-sd.img.xz`, its companion `.sha256`, `SHA256SUMS`,
`QUICKSTART.md`, `RELEASE.md`, build/SD/release manifests and
`source-materials.tar.gz`. QSPI byproducts, build logs and unrelated workspace
files are excluded. Only metadata is uploaded as an Actions artifact.

Preparation checks the image size/hash against the SD manifest, build-source
hashes against the checkout, and the source inventory's exact commit, file set
and hashes. Extra source files and symlinks are refused. Checksums cover all
attached files except `SHA256SUMS` itself. Individual assets must be below 2 GiB;
a larger source bundle requires a separate splitting change, not omission of sources.
Before upload, the complete asset set and checksums are checked again. The upload
always requests a draft/prerelease at the exact commit, then checks draft state,
asset names/sizes and server-provided digests when available. API errors other
than an expected missing tag/release stop the operation. A failed upload can
leave an incomplete private draft: inspect it and retry with a fresh tag; the
workflow does not overwrite or delete existing releases.

## Before publication

Each new build starts with `hardware_validated: false` and distribution review
incomplete, even if a previous image was tested. Complete the exact-image checks,
including cold boot and the documented SSH/RX limits, and update the release
notes with the image hash and qualification record. Reconcile runtime notices
and the vendor BOOT.BIN/FSBL/FPGA sources/permissions described in the
[licensing audit](licensing.md). The software-source collector is review material,
not complete vendor clearance. Publication is a separate maintainer action.

The generated quick start covers download/checksum, microSD writing and the
stock lab Ethernet/login defaults. It directs users to the actual release notes
for qualification rather than borrowing historical lab-image results.
