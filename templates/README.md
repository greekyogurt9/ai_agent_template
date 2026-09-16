# templates/ — shared deck assets (placeholder)

Assets the optional **deck mode** clones when it builds a stakeholder presentation.

| file | role |
|---|---|
| `Template.pptx` | a **neutral, brand-free placeholder** deck skeleton (title slide + one takeaway-title content slide) |
| `make_placeholder_deck.py` | the generator that produced `Template.pptx` — included so the binary isn't opaque; run it to regenerate |

## Swap in your own

`Template.pptx` here is intentionally generic — no logo, no brand colors, no author metadata. **Replace it
with your own branded `.pptx`** (keep the filename) and the deck builder will clone yours instead. That's the
whole idea: your branding never has to live in this repo, and this placeholder gives the deck mode something
concrete to point at out of the box.

## Regenerate the placeholder

```bash
python3 templates/make_placeholder_deck.py     # requires python-pptx
```

> Note: the deck **builder** itself (`agent/create_deck.py`) is a stub described in `agent/README.md`, not
> implemented here. This folder only provides the blank canvas it would use.
