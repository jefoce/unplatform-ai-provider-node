---
name: "ideogram-4-director"
description: "Author copy-paste-ready structured JSON prompts for the local Ideogram 4 text-to-image flow."
---

# Ideogram 4 Director

Style first. Detect the requested look, commit to one medium and one art direction, then write the JSON. Do not force photorealism when the brief asks for anime, 3D, illustration, poster art, or a painterly treatment.

Ideogram 4 is trained on structured JSON captions. JSON gives control over composition, palette, layout, and literal text. Its strongest feature is in-image text: signage, logos, captions, watermarks, multi-line copy, and multilingual scripts.

Natural-language prompts are a fallback in the hosted product, where a magic-prompt layer converts them to JSON. The official open-weight guide says plain text will not work well and may trigger a safety warning. For this local flow, always emit JSON.

## WORKFLOW

1. Read the request. Extract subject, action, setting, style, visible text, layout, colors, and mood.
2. Reject references. If the user supplies `@Image N`, `@Video N`, or `@Audio N`, explain that this flow is text-to-image only, then describe the subject in words. Do not emit reference labels.
3. Detect style. Map the brief to one `medium`: `photograph`, `illustration`, `3d_render`, `painting`, or `graphic_design`.
4. Build the caption in fixed key order. Use the three documented top-level keys. Put `background` before `elements`.
5. Validate. Parse the JSON, check key order, check exactly one of `photo` or `art_style`, check `bbox` integers, check uppercase hex.
6. Output one JSON object. No markdown fence, no commentary, no placeholders, no settings prose.
7. Run the quality check before sending.

## MODE

Text-to-image only. No image references, no image editing, no character sheets, no video, no audio, no negative prompt.

The app controls resolution, aspect ratio, steps, sampler, shift, and guidance. Never write CFG, step count, sampler name, shift, or `--ar` into the prompt. Never write a negative prompt. Express exclusions as positive scene facts: "an empty street" instead of "no people".

If the brief is ambiguous, choose the medium that fits the subject. Use `photograph` for ordinary real-world scenes only. Use `illustration`, `3d_render`, or `painting` for fantastical, stylized, or impossible subjects when no medium is stated.

## JSON PROMPT SCHEMA

Three top-level keys. Use this order.

| Key | Type | Required | Notes |
|---|---|---|---|
| `high_level_description` | string | No, strongly recommended | One or two sentences. Summary only. |
| `style_description` | object | No, strongly recommended | Style, lighting, medium, palette. |
| `compositional_deconstruction` | object | Yes | Must contain `background` and `elements`. |

`style_description` must contain exactly one of `photo` or `art_style`. Key order is strict.

Photo order: `aesthetics`, `lighting`, `photo`, `medium`, `color_palette`.

Non-photo order: `aesthetics`, `lighting`, `medium`, `art_style`, `color_palette`.

| Style key | Type | Required | Notes |
|---|---|---|---|
| `aesthetics` | string | Yes, when style block is present | Mood and aesthetic keywords. |
| `lighting` | string | Yes | Light direction, quality, time of day. |
| `photo` | string | Yes for photo | Camera, lens, aperture, angle, depth of field. |
| `medium` | string | Yes | `photograph`, `illustration`, `3d_render`, `painting`, `graphic_design`. |
| `art_style` | string | Yes for non-photo | Genre, line, shading, renderer, brushwork, graphic system. |
| `color_palette` | list[string] | No | Uppercase `#RRGGBB`. Up to 16 colors. |

`compositional_deconstruction` order: `background`, then `elements`.

Every element is `obj` or `text`.

| Element key | Type | Required | Notes |
|---|---|---|---|
| `type` | string | Yes | `obj` or `text`. |
| `bbox` | list[int] | No | `[y_min, x_min, y_max, x_max]`, integers 0 to 1000. |
| `text` | string | Yes for text | Exact characters to render. |
| `desc` | string | Yes | Detailed visual description. |
| `color_palette` | list[string] | No | Uppercase `#RRGGBB`. Up to 5 colors. |

`obj` order: `type`, `bbox`, `desc`, `color_palette`.

`text` order: `type`, `bbox`, `text`, `desc`, `color_palette`.

String rules:

- Use a JSON object with double-quoted keys and strings.
- Escape `"` as `\"` and `\` as `\\`. Write a line break inside one text block as `\n`.
- Keep non-ASCII characters literal. Do not use `\uXXXX` escapes.
- No trailing commas.
- Hex colors must be uppercase six-digit `#RRGGBB`. Lowercase and shorthand are rejected.
- Do not add `aspect_ratio`. The app sets the frame. The open-source magic prompt may emit it, but it is not part of the caption schema.
- Unknown keys and out-of-order keys produce verifier warnings.

Minimal valid example:

```json
{
  "high_level_description": "A single red apple on a pale wooden table in a plain studio.",
  "compositional_deconstruction": {
    "background": "A plain warm grey studio wall and a pale wooden tabletop.",
    "elements": [
      {"type": "obj", "desc": "A ripe red apple with a short green stem, glossy skin, soft contact shadow."}
    ]
  }
}
```

## TEXT RENDERING

Every visible string gets its own `text` element.

`text` holds the exact characters. `desc` holds typography, size, color, position, orientation, and effects. Never put the literal string only in `desc`. That is the most common cause of missing or garbled text.

Use `\n` for line breaks inside one block. Use separate elements for visually separate blocks: headline, subhead, label, caption.

Typography controls in `desc`:

- One typeface category: serif, sans-serif, display, script, or monospace.
- One weight: light, regular, medium, bold.
- One style: italic or upright.
- Size and hierarchy: "huge", "small", "caption-scale".
- Color and contrast.
- Position, alignment, rotation, outline, shadow, embossing.

Language: write prose fields in English. Keep the `text` field in the user's requested language. Preserve diacritics, capitalization, punctuation, and non-Latin scripts exactly.

Ideogram 4 handles dense small copy, paragraphs, multilingual scripts, rotated text, and inverted text better than most models. It still fails on long unbroken stylized strings. Break hero titles at natural word boundaries with `\n` to reduce typos and dropped letters.

Failure cases:

- Literal copy hidden in `desc`: text may be ignored.
- Long single-line display type: typos, dropped characters.
- Tiny text with a small `bbox`: unreadable glyphs.
- Overlapping text boxes: merged or clipped text.
- Malformed JSON or missing `high_level_description`: hosted API may treat the prompt as plain text. Local behavior is not documented, so validate anyway.
- Non-JSON prompts: higher false-positive rate on the safety filter.

## STYLE LAYER

Photoreal only when requested or when the brief is an ordinary real-world scene.

Photoreal: `medium: "photograph"`, use `photo` for camera and lens, keep lighting physical, include a restrained grade. Do not add painterly or anime terms.

Anime and illustration: `medium: "illustration"`, use `art_style` for genre and craft. Example: "anime key visual, clean line art, cel shading, detailed background art". Name the genre once.

3D and CGI: `medium: "3d_render"`, use `art_style` for renderer, materials, and lighting. Example: "octane render, brushed metal, subsurface scattering, studio HDRI".

Poster and graphic design: `medium: "graphic_design"`, use `art_style` for grid, vector treatment, print texture, and type system. Put every headline and label in `text` elements. This is the strongest use case for the model.

Painterly and stylized: `medium: "painting"`, use `art_style` for paint medium, brushwork, and edge quality. Example: "oil on canvas, visible brushwork, soft edges, impasto highlights".

Do not mix `photo` and `art_style` in one caption. Do not put camera language in a non-photo `art_style` caption. Keep the style detail in `style_description`, not scattered across every element.

## PROMPT TEMPLATES

### Poster

```json
{
  "high_level_description": "A bold summer music festival poster with a sunburst and stacked headline.",
  "style_description": {
    "aesthetics": "retro, warm, high contrast",
    "lighting": "flat even light",
    "medium": "graphic_design",
    "art_style": "screen-printed poster, halftone texture, heavy geometric shapes",
    "color_palette": ["#F25C2A", "#FFD166", "#1B1B2F", "#F7F3E8"]
  },
  "compositional_deconstruction": {
    "background": "A flat burnt-orange field with a large pale yellow sun disc centered behind the type.",
    "elements": [
      {"type": "text", "bbox": [120, 80, 380, 920], "text": "SUMMER\nNIGHTS", "desc": "Huge condensed sans-serif headline, cream, stacked two lines, centered.", "color_palette": ["#F7F3E8"]},
      {"type": "text", "bbox": [420, 180, 500, 820], "text": "LIVE MUSIC - AUG 12", "desc": "Small bold sans-serif subhead, dark navy, centered under the headline.", "color_palette": ["#1B1B2F"]}
    ]
  }
}
```

### Product Shot

```json
{
  "high_level_description": "A studio product photograph of matte black wireless earbuds in an open charging case on wet slate.",
  "style_description": {
    "aesthetics": "premium, minimal, cool",
    "lighting": "softbox key from upper left, thin rim light, dark falloff",
    "photo": "100mm macro, f/8, low angle, shallow reflection",
    "medium": "photograph",
    "color_palette": ["#0B0B0D", "#2E3138", "#8A8F98", "#F2F4F7"]
  },
  "compositional_deconstruction": {
    "background": "A dark slate surface with a thin film of water and a black seamless backdrop.",
    "elements": [
      {"type": "obj", "bbox": [300, 260, 780, 740], "desc": "An open matte black charging case with two stemless earbuds seated inside, fine seam lines, soft specular highlights.", "color_palette": ["#0B0B0D", "#2E3138"]}
    ]
  }
}
```

### Scene

```json
{
  "high_level_description": "An anime illustration of a quiet Tokyo backstreet at dusk after rain.",
  "style_description": {
    "aesthetics": "nostalgic, quiet, cinematic",
    "lighting": "blue hour ambience, warm shop light spill, wet reflections",
    "medium": "illustration",
    "art_style": "anime background art, clean line art, cel shading, detailed urban props",
    "color_palette": ["#1B2A41", "#2F5D8C", "#F2A65A", "#E8E1D5"]
  },
  "compositional_deconstruction": {
    "background": "A narrow Japanese backstreet with low buildings, vending machines, overhead wires, and rain-slick pavement reflecting blue and amber light.",
    "elements": [
      {"type": "obj", "bbox": [380, 520, 900, 760], "desc": "A girl in a cream raincoat and dark skirt walking away from camera, holding a clear umbrella, seen from behind.", "color_palette": ["#E8E1D5", "#1B2A41"]},
      {"type": "text", "bbox": [210, 120, 290, 360], "text": "RAMEN", "desc": "Small warm-white illuminated sign in a shop window, vertical layout, sans-serif.", "color_palette": ["#F2A65A"]}
    ]
  }
}
```

### Portrait

```json
{
  "high_level_description": "A natural-light portrait of a woman in a grey knit sweater against a plain wall.",
  "style_description": {
    "aesthetics": "natural, calm, understated",
    "lighting": "soft window light from camera left, gentle shadow falloff",
    "photo": "85mm, f/2, eye level, shallow depth of field",
    "medium": "photograph",
    "color_palette": ["#D9D2C7", "#8A8178", "#3B3A38", "#F4F1EC"]
  },
  "compositional_deconstruction": {
    "background": "A plain warm grey plaster wall with subtle texture.",
    "elements": [
      {"type": "obj", "bbox": [120, 280, 900, 720], "desc": "A woman with shoulder-length dark hair, medium skin tone, wearing a charcoal grey knit sweater, relaxed expression, looking slightly off camera.", "color_palette": ["#3B3A38", "#8A8178"]}
    ]
  }
}
```

## QUALITY CHECK

- JSON parses. No trailing commas, no comments, no markdown fence.
- Top-level keys are only `high_level_description`, `style_description`, `compositional_deconstruction`, in that order.
- `compositional_deconstruction` exists and has `background` before `elements`.
- `style_description` has exactly one of `photo` or `art_style`, with the correct key order.
- Every element has `type` and `desc`. Every text element has `text`.
- Every `bbox` has four integers in 0 to 1000, with lower coordinate first on each axis.
- Every palette is uppercase `#RRGGBB`, at most 16 image colors and 5 element colors.
- Every visible string is in a `text` field, character for character. Typography is in `desc`.
- The requested style is respected. Photorealism is not the default.
- No references, no negative prompt, no settings prose, no placeholders.
- Important elements come first. No fixed element cap is documented, but long prompts can lose late elements in the hosted product, and local behavior is uncertain.
- Overlapping `bbox` z-order is not documented. Avoid overlaps unless the layout needs them.
