# Why the configurator looks and behaves like this

The page is a tool, not a shop window: it exists so that picking firmware
features and writing a card is quick and hard to get wrong. The rules below come
from published usability and accessibility guidance, and each is marked with
whether this codebase actually follows it.

Legend: **done** = implemented here, **partial** = partly, **not done** = known gap.

## Hierarchy and scanability

| Rule | Where it comes from | Here |
|---|---|---|
| One vertical list per group, group titles always visible, collapsible by keyboard | [GOV.UK checkboxes](https://design-system.service.gov.uk/components/checkboxes/) | **done** - six groups, headers are role=button with aria-expanded and Enter/Space |
| Three type sizes only: group heading, option label, metadata | [NN/g visual hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/) | **done** - .72rem headings, .9rem names, .78-.82rem metadata |
| Every option row is one label, so the whole row is the hit target | [web.dev tap targets](https://web.dev/articles/accessible-tap-targets) | **done** - the label wraps the input |

## Feedback while waiting

| Rule | Source | Here |
|---|---|---|
| Under a second: no spinner. Seconds: inline busy label, leave the layout still | [NN/g response times](https://www.nngroup.com/articles/response-times-3-important-limits/) | **done** - buttons go busy and aria-busy, the grid does not move |
| Long jobs need stepped progress, not a spinner | [NN/g progress indicators](https://www.nngroup.com/articles/progress-indicators/) | **done** - the job card shows the phase (configuring, compiling, writing) plus the live log |
| Loading content keeps its space | [NN/g skeleton screens](https://www.nngroup.com/articles/skeleton-screens/) | **partial** - the feature list shows a loading line in place; cards are sized from the start |

## Controls

| Rule | Source | Here |
|---|---|---|
| Label above the control, hint underneath, described by it | [NN/g web form design](https://www.nngroup.com/articles/web-form-design/) | **done** |
| Mutually exclusive choices are radios, all visible at once - not a select | [NN/g checkboxes vs radios](https://www.nngroup.com/articles/checkboxes-vs-radio-buttons/) | **done** for the mesh size (four radios); the machine and version pickers stay selects because their lists are long |
| Focus is always visible, about 2 px with offset | [GOV.UK focus states](https://design-system.service.gov.uk/get-started/focus-states/) | **done** - focus-visible on every interactive element, and slash jumps to the filter |

## Accessibility

| Rule | Source | Here |
|---|---|---|
| AA contrast on dark: 4.5:1 for text, 3:1 for large text and icons | [web.dev colour contrast](https://web.dev/learn/accessibility/color-contrast) | **done** for the palette in use: #e7ecf5 on #0b0f16 is about 16:1, muted #8b97ab about 6:1 |
| One persistent polite live region for job status | [MDN live regions](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions) | **done** - the phase line is role=status with aria-live=polite, as are toasts |
| Respect reduced motion | [web.dev prefers-reduced-motion](https://web.dev/articles/prefers-reduced-motion) | **done** - transitions are switched off wholesale under the media query |

## Errors and empty states

| Rule | Source | Here |
|---|---|---|
| Say cause and fix next to the thing that failed | [GOV.UK error message](https://design-system.service.gov.uk/components/error-message/) | **done** - for example "12 is outside the mesh sizes this firmware can build (3..9) ... 10 or more cannot link", and failures point at the log |
| An empty list explains itself and offers the action | [NN/g empty states](https://www.nngroup.com/articles/empty-state-interface-design/) | **done** - "No features match x" plus a Clear filter button |

## Trust, for something that writes firmware and cards

| Rule | Source | Here |
|---|---|---|
| Check your answers before committing | [GOV.UK check answers](https://design-system.service.gov.uk/patterns/check-answers/) | **done** - the write dialog is a summary table: machine, firmware, mesh, image size, feature changes, screen pair, device |
| Confirmation only for destructive acts, consequence named in the button | [NN/g confirmation dialogs](https://www.nngroup.com/articles/confirmation-dialog/) | **done** - "Erase /dev/sdX and write"; nothing else asks |
| Keep the primary button reachable when it cannot run, and say why | [NN/g button states](https://www.nngroup.com/articles/button-states-communicate-interaction) | **done** - the build button stays focusable with aria-disabled and prints the reason underneath; pressing it shows the reason as a toast |

## Small things

| Rule | Source | Here |
|---|---|---|
| Animate only transform and opacity, 120-180 ms | [web.dev animations guide](https://web.dev/articles/animations-guide) | **done** - the budget bar fills with scaleX, not width |
| Tabular numerals where digits change | [MDN Intl.NumberFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat) | **done** - monospace figures use font-variant-numeric: tabular-nums, numbers go through toLocaleString |
| One-click copy for things people retype | [MDN Clipboard.writeText](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText) | **done** for the sha256 |

## Known gaps, honestly

- The version list is fetched on load; a slow GitHub answer leaves that select
  empty for a moment and the note under it says so.
- No light theme: this is a dark tool because it lives next to a terminal.
- Job progress is phase level, not per second: PlatformIO prints freely, so the
  page shows its phases and the log rather than inventing a percentage.

