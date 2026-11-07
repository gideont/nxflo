# Nexusflow CSV Viewer

Adapted from https://github.com/gideont/csv-viewer, component revision 1427ac564570353f69d74e1c505888215c32af7e.
Preserves local CSV/Excel parsing, worksheet selection, virtualized rows, sorting,
column sizing, density, pagination, and display controls. Defaults to Nexusflow's
light theme and uses the shared site header/footer. All dependencies are bundled
locally; opening files requires no network requests.

Rebuild from this directory with `npm ci && npm run build`. Commit the generated
`../csv-viewer.js` and `../csv-viewer.css` so the static Docker build needs no Node
runtime. The lockfile records dependencies; `../csv-viewer-LICENSES.txt` contains
third-party license notices. SheetJS uses version 0.20.3.
