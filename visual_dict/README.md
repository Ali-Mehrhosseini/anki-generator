Visual Dictionary — static card generator

This small tool creates a static HTML visual-dictionary card for an image with an Italian label and English translation.

Quickstart

1. Put your image somewhere local (e.g. `~/Downloads/pic.jpg`) or in the project.
2. Run the generator:

```bash
python visual_dict/create_card.py --image /path/to/pic.jpg --italian "la panna" --english "cream" --output out_cards
```

3. Open the generated HTML in `out_cards/la_panna.html` in your browser.

Notes

- The script copies the image into `out_cards/assets/` and writes one HTML file.
- The template is `visual_dict/template.html`. Edit it to change layout/styling.
- If you want automated image resizing you can install Pillow and extend the script.

If you'd like, I can:
- Add batch mode to create many cards at once from a CSV file.
- Add optional image resizing (Pillow) and smart stress-dotging for Italian.
- Integrate TTS audio or generate a printable PDF gallery.
