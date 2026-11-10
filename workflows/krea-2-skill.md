---
name: "krea-2-director"
description: "Author copy-paste Krea 2 prompts for text-to-image and 1-2 style references."
---

# Krea 2 Director

Krea 2 is an aesthetic-first model that follows natural language and style direction. Choose the style explicitly. Write the style the user asked for. Write photoreal only when the user asks for photoreal.

This app runs one prompt per image. There is no prompt expansion step and no negative prompt. Every word must do visible work in the first pass.

## WORKFLOW

1. **Read inputs.** Separate the user's content request from the style request. Content is what must exist. Style is how it must look.
2. **Detect mode.** Count attached references. Zero is text-to-image. One or two is style-reference mode. Never invent a reference.
3. **Detect style.** Use the user's named style. If the user names none, infer the medium from the subject and state it plainly. Do not silently default to photoreal.
4. **Build reference map.** Give each reference one job. `@Image 1` might carry palette and texture. `@Image 2` might carry line weight and shading. Never give two references the same job.
5. **Write.** One or two paragraphs of prose. Content first, style anchors last. Use reference labels only where they apply.
6. **Quality check.** Run the checklist before returning. Then return the prompt alone.

## MODES

### Text-to-image

No references. The prompt carries content and style. Krea 2 tolerates short prompts, but this app gives one shot. Write the detail you want now. Keep short prompts for cases where the user explicitly wants the model to choose the interpretation.

### One style reference

The reference supplies look. The prompt supplies a new subject.

A style reference transfers palette, tonal range, contrast, texture and grain, line quality, brush or render finish, lighting feel, and broad composition cues. It transfers the painted-or-photographic feel of the source.

It does not transfer subject identity, exact pose, exact objects, exact layout, or readable text. It is a style input. Do not treat it as an identity lock. Describe faces and characters explicitly when they must stay consistent.

At full strength the reference can override prompt color. Do not fight it. Choose subjects that can live in the reference palette.

### Two style references

Both references are active. The LoRA used here was trained for one or two reference images and needs no trigger word. Give each reference a separate, non-overlapping role. If both carry palette, the blend can turn muddy.

State each role in the prompt. Example: `@Image 1` leads palette and surface, `@Image 2` leads line and shading. Style weight is set by the app. Do not write strength numbers or weight instructions into the prompt.

## GENERAL WRITING RULES

- **Use natural language.** Full sentences or descriptive fragments. Krea 2 understands spatial relations and material language in prose. Avoid comma-stuffed tag clouds.
- **Be concrete.** Name materials, surfaces, light direction, color, and wear. Write "brushed steel with fine scratches" instead of "nice metal".
- **Long and specific wins when control matters.** Official guidance says long detailed prompts yield the best results, especially at high resolution. Every sentence must add a visible fact.
- **Order the description.** Subject and action, appearance and clothing, props and materials, composition and camera, environment, light and color, medium and finish.
- **Separate style from content.** One clause for the scene. One clause for the look. Do not bury style inside every noun.
- **Quote text to render.** Put exact words in double quotes. Keep them short. Example: a shop sign that reads "OPEN LATE".
- **No meta-commentary.** Do not write "this image shows", "here is", "a picture of", or "the prompt is".
- **No ad language.** Drop "stunning", "breathtaking", "viral", "masterpiece", "8k", "best quality". These add no visual fact.
- **No negative phrasing.** Krea 2 Turbo is classifier-guidance free at CFG 1. There is no negative channel. Describe the desired state: "clean empty wall" instead of "no posters".
- **No lists in the final prompt.** Prose reads as one scene. Bullets read as keywords.

## REFERENCE LABELS

- Use only `@Image 1` and `@Image 2`.
- One role per reference. State the role in the same sentence as the label.
- The app converts these labels to model-internal tokens. Never write internal picture placeholders, angle-bracket image tokens, or LoRA trigger words.
- Do not describe the reference image at length. Name the trait to borrow.
- Do not write `@Image 3`. This app accepts at most two references.
- Place labels before the content they modify, not in a separate reference list.

Example: `@Image 1 sets the palette, paper grain, and flat ink finish.`

## STYLE LAYER

### Photoreal

Use only when requested. Name the photographic mode, the light source and quality, the lens feel, and the surface truth. Include skin texture, fabric wear, dust, and reflections. A neutral color process reads more real than a saturated one.

### Anime and illustration

Name the tradition and the genre. Say cel animation, ligne claire, flat color, screentone, or watercolor illustration. Describe line weight, shading model, and palette. Do not add photoreal surface detail.

### 3D and CGI

Name the render finish: matte vinyl, brushed metal, subsurface skin, clay, or stylized toy. Describe how light sits on the surface. Name the lighting setup only if it changes the look.

### Painterly and stylized

Name the medium and the mark: oil, gouache, ink wash, stipple, or screen print. Describe brush behavior, edge quality, and surface texture. Keep the subject readable through the style.

### Style reference interaction

Let the reference carry the finish. The prompt carries content plus one or two anchors such as light direction or palette family. Do not name a second medium that competes with the reference. If you must name one, state the hierarchy: `@Image 1 leads the finish, the prompt supplies subject and light.`

## PROMPT TEMPLATES

### Text-to-image

```text
[Subject and action]. [Appearance and clothing]. [Props and materials]. [Composition and camera]. [Environment]. [Light, color, mood]. [Medium and finish].
```

Worked example:

```text
Close-up portrait of a ceramicist at a wheel, clay wet on both hands, thin apron over a charcoal shirt, short grey hair dusted with clay, three finished bowls on a plank behind her, soft north window light from the left, cool grey shadows, warm skin, 50mm lens feel, shallow depth of field, matte film finish.
```

### One style reference

```text
@Image 1 sets [palette, texture, finish]. [New subject and action]. [Appearance and materials]. [Composition and environment]. [Light and mood]. Keep [one anchor] from the prompt.
```

Worked example:

```text
@Image 1 sets the muted teal and bone palette, coarse halftone dots, and paper grain. A heron stands in shallow reeds at dawn, long neck folded, pale grey feathers with a faint blue cast, water flat and dark, low mist, soft side light, quiet mood, screen-print finish.
```

### Two style references

```text
@Image 1 sets [role A]. @Image 2 sets [role B]. [New subject and action]. [Appearance and materials]. [Composition and environment]. [Light and mood].
```

Worked example:

```text
@Image 1 sets the warm dusk palette and rough paper texture. @Image 2 sets the heavy black outlines and flat color. A market stall at dusk, stacked citrus crates, a vendor in a red apron closing a cash box, warm bulbs overhead, deep blue street behind, low angle, crowded frame, graphic illustration finish.
```

## QUALITY CHECK

- Mode matches the reference count. Zero, one, or two. Nothing else.
- Only `@Image 1` and `@Image 2` appear. No internal tokens, trigger words, or strength values.
- Each reference has exactly one role. The roles do not overlap.
- The reference is used for style, not for copying its subject or identity.
- Style is either delegated to the reference or stated in the prompt. Not both fighting.
- Every content claim is concrete. No vague praise, no ad words, no meta lines.
- Text to render is in double quotes and short.
- No negative phrasing and no negative prompt.
- The change from the user's request is unambiguous. The prompt can be pasted as-is.
- The prompt contains no headings, bullets, notes, or explanations.
