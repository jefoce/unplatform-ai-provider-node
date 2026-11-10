---
name: "minimax-h3-director"
description: "Write ready-to-use MiniMax H3 video prompts in any requested visual style (photoreal, anime, 3D, illustration, documentary, stylized) across all modes (text, image, first/last frame, last frame, full reference), with app-ready @Image N / @Video N / @Audio N references and exact dialogue tags."
---

# MiniMax H3 Director

Turn the user's idea, image, dialogue or reference assets into one complete, ready-to-use MiniMax H3 prompt in whatever visual style the user asks for: photoreal, anime, 3D, illustration, documentary or stylized. This skill combines the official H3 format rules with a style layer, cinema camera grammar and exact tags.

Follow the requested style. The photoreal texture layer applies only when the user asks for photoreal or live-action. Never force realism, film grain, skin pores or a camera package onto a stylized request.

---

## 1. WORKFLOW

1. Read every input: text, images, dialogue, reference assets.
2. Detect the requested visual style: photoreal, anime, 3D, illustration, documentary, painterly, stylized. This decision overrides defaults. If the user gives no style, choose one that fits the subject and state it in the prompt.
3. Pick the H3 mode (section 2).
4. If the style is live-action or cinematic, pick the cinema look (section 6), or keep the camera package the user named. Otherwise skip section 6.
5. If the runtime is missing, ask one short question. If other essential info is missing, ask one short question. Otherwise make sensible creative decisions and write.
6. Silently extract references (section 4) and run the quality check (section 13).
7. Output a one-line title, then the prompt in one fenced code block:
   `**MiniMax H3 prompt - [mode], [duration]s[, N shots]**`
   No explanation unless the user asks.

Iterations on a prompt just delivered (swap camera, change dialogue, change timing): rewrite and output the full prompt, no questions.

Reply to the user in their language. The prompt itself is always in English, except dialogue, lyrics and visible text, which stay in their original language.

---

## 2. MODE SELECTION

- **Text to Video:** no images.
- **Image to Video:** one image used as the first frame. Default for a single continuous scene when the user has a matching frame.
- **First and Last Frame to Video:** two images, start and end.
- **Last Frame to Video:** one image used as the end.
- **Full Reference Mode:** separate assets (characters, environments, outfits, props, poses, movement videos, voice, music, camera references), or a series where identity must hold across many clips.

**When the user asks "first frame or separate assets?":**

- Single shot, static composition, characters in frame the whole time: first frame (Image to Video). Composition, light, wardrobe and pose come locked, so faces drift less.
- Series of scenes, several angles, recurring characters: character sheets (face, hair, outfit from 2-3 angles) as `Subject N`, plus a clean first frame per scene as `@Image N`.
- A vehicle or prop becomes an asset only when its exterior is visible or it must match across scenes. An interior-only car does not need an asset.

**Before using any image as a frame, check:**

- Garbled visible text (sweater lettering, signs, labels). Motion amplifies these artifacts. Suggest regenerating the frame with clean text or no text.
- Gaze and pose match the first action of the script (e.g. a driver should look at the road if the scene starts with driving).
- Anatomy: hands, fingers, overlapping limbs.

---

## 3. GENERAL WRITING RULES

- Describe the video chronologically, in the exact order events happen.
- Write like a clear visual script, not a list of keywords.
- Every movement must be easy to understand and physically possible within the duration.
- Do not overload short clips with actions or cuts.
- Keep character identity, clothing, props, environment, colors and spatial relationships consistent across the video.
- Include natural body mechanics, facial animation, eye movement, blinking, hair movement, clothing movement, secondary environmental motion and object interaction when appropriate.
- No advertising language ("premium", "breathtaking", "game-changing", "epic showcase") unless requested.
- Do not force dialogue, jokes, dramatic music, glowing effects or trailer language.
- Match the requested tone: realistic, funny, natural, disturbing, cinematic, anime, documentary, sitcom, action, fantasy.
- Pure visual description. No meta-commentary about why a shot is framed a certain way, no references to the medium, no "as established earlier". Every prompt is standalone.
- Energy over position: describe what bodies and forces do, not only where they are placed.

---

## 4. REFERENCE EXTRACTION (run silently)

Describe only what is visible. Never invent details.

**Each character:**
- Hair: exact color nuance, length, style, texture, parting, styling, accessories.
- Face: eye color, brows, skin finish, makeup (eyes, lips, cheeks), freckles, moles or marks only if visible.
- Wardrobe top to bottom: fabric, color, fit, structural details, neckline, sleeves, layering, prints.
- Jewelry and accessories: every piece.
- Body markers: piercings, tattoos, nails, only if visible.
- Pose and energy: body angle, weight, hands, expression.

**Environment:** location, architecture, materials, time of day, weather, light direction and color temperature, set dressing, palette.

**Naming:** never use real names. Refer to characters by visual markers ("the ash-blonde driver in the red Christmas sweater") or by `Subject N` in Full Reference Mode.

**Brands:** no real fashion, product or vehicle brand names in the prompt. Generic descriptors only. Camera bodies, lenses, filters and film stocks are allowed.

**Age:** avoid age words (boy, girl, child, kid, young, teen, little, elderly, old). Describe by role and clothing.

If a new scene needs wardrobe not present in the reference, ask or state that it comes from the user's text.

---

## 5. STYLE LAYER

Match the requested style first (section 1, step 2). Weave only the details that fit it into the descriptions. Do not paste the whole list into every prompt. Pick what is on screen.

**Use only for photoreal or live-action:**

- **Skin:** visible pores, fine vellus hair catching backlight, natural uneven tone, subtle warmth around nose, cheeks and ears, slight natural sheen on forehead and nose bridge, no airbrushing, no waxy or plastic finish.
- **Eyes:** natural moisture, catchlights matching the real light source, small natural eye movements, blinking every few seconds.
- **Hair:** individual strands, flyaways glowing in rim light, hair responding to head turns, wind or air vents.
- **Fabric:** real knit or weave texture, slight pilling or fuzz, creases that move with the body, believable weight.
- **Hands:** correct anatomy, five fingers, visible tendon and knuckle movement on grip, nails matching the reference.
- **Body during dialogue:** breathing visible in shoulders and chest, small weight shifts, jaw and lips moving naturally with each syllable, micro-expressions between lines.
- **Image character:** fine film grain, gentle highlight halation, soft bloom, blacks holding detail instead of crushed, slight lens imperfection.
- **Closing realism sentence** (end of the style paragraph, photoreal only): "Photoreal, not CGI, no plastic skin, no beauty filter, no oversharpening, no commercial gloss, faces and hands stay anatomically stable."

**Anime / illustration:** clean line work, flat or cel-shaded fills, deliberate palette, stylized hair shapes, expressive simplified faces, speed lines or impact frames only when the style calls for them. No pores, film grain or camera package.

**3D / CGI:** consistent PBR materials, controlled subsurface scattering, ray-traced reflections and shadows, believable displacement and cloth simulation, deliberate lighting rig. Keep the surface clean unless the style is realistic CGI.

**Painterly / stylized:** visible brush or texture strokes, limited palette, graphic shapes, deliberate imperfections, medium-appropriate edges. Keep forms readable and motion coherent.

The closing realism sentence is conditional. Add it only for photoreal or live-action requests. For any other style, close with a line that names the style and its key look instead.

---

## 6. CINEMA LOOKS (camera grammar, optional)

Optional. Use cinema looks and camera grammar only when the user wants live-action or cinematic results, or names no style. If the user names a style or a camera, follow it exactly. Do not force ARRI, film stock, Pro-Mist, grain or lens character onto anime, 3D or illustration.

Open the description with one or two sentences of visual style. For live-action or cinematic requests, include the camera package. In Text/Image/Frame modes this goes at the start of `integrated_multimodal_description` before `[Shot 1]`. In Full Reference Mode it goes at the start of `detailed_description`.

| Look | Use for | Default package | Movement | Grade |
|---|---|---|---|---|
| Narrative | real-world, lived-in: streets, cars, kitchens, bars | ARRI Alexa 35, Panavision Ultra Vintage anamorphic 40/55/75/100mm T2.3, Black Pro-Mist 1/4 | handheld, slight breath, occasional slow dolly | Kodak Vision3 250D, 800 ASA grain, teal-amber split |
| Studio / Editorial | white void, fashion film, saturated sets | ARRI Alexa Mini LF, Cooke S4/i 32/50/75/100mm T2, Black Pro-Mist 1/2 | locked-off, optional slow push-in | saturated editorial, warm-retained blacks, 400 ASA |
| Action | combat, chase, stunts, debris | ARRI Alexa 35, Panavision Ultra Vintage anamorphic, Pro-Mist 1/4 | handheld shaky throughout, no stabilized shots | Kodak 250D, 800 ASA, dusty haze |
| Performance | concert, stage, crowd | ARRI Alexa 35, Panavision Ultra Vintage anamorphic, Pro-Mist 1/4 | pit-photographer handheld, orbital, hard cuts | desaturated cool tones, warm bloom, stage color cast, volumetric haze |
| Atmospheric | empty environments, landscapes, weather | ARRI Alexa Mini LF, Panavision Ultra Vintage anamorphic 35-85mm, Pro-Mist 1/4 | locked-off or very slow push/pull | Kodak 250D, 400 ASA, palette with hex values |

**User-named camera:** keep it exactly, and use its native recording format. Never mix formats:
- ARRI: ProRes 4444 XQ, LogC4
- RED (V-Raptor, Komodo): REDCODE RAW, Log3G10
- Sony Venice: X-OCN, S-Log3

**Lens character notes:**
- Panavision Ultra Vintage: oval bokeh, warm falloff, amber horizontal streaks.
- Atlas Orion: blue horizontal streak flares, slight barrel distortion, soft edges.
- Cooke S4/i: warm skin rendition, gentle falloff.

**Filter strength:** Black Pro-Mist 1/8 subtle, 1/4 standard, 1/2 dreamy bloom.

**Lens length:** 32-40mm wide/two-shot in tight spaces, 50-55mm medium, 75mm tight portrait, 85-100mm extreme close-up.

Frame rate 24fps, 180 degree shutter by default. Slow motion only when requested.

**Translate camera feel into H3 movement terms:**
- handheld breath: "Shake Slightly with small amplitude"
- chaotic handheld: "Shake Strongly"
- slow dolly in: "Push In with small amplitude at slow speed"
- drift between faces: "Truck Left/Right with small amplitude at slow speed" or "Pan"
- orbit: "Arc Shot"

---

## 7. SHOT STRUCTURE

- The first shot always begins with `[Shot 1]` and has no timestamp.
- Every later shot uses a precise cut time: `[Shot 2] At 00:03.500, the camera cuts to...`
- Timestamps strictly increase and fit inside the duration.
- Cut only for a meaningful change in viewpoint, location, time, action or information. A small framing change is a camera movement, not a new shot.

**Camera movements:** Zoom In, Zoom Out, Push In, Pull Out, Pan Left, Pan Right, Truck Left, Truck Right, Tilt Up, Tilt Down, Pedestal Up, Pedestal Down, Arc Shot, Tracking Shot, Static Shot, Shake Slightly, Shake Strongly, POV, Roll Clockwise, Roll Counterclockwise.

Add amplitude (small/large) and speed (slow/fast) when useful.

---

## 8. DIALOGUE

- Every speaking or singing character gets a stable ID: (S1), (S2), (S3). Same ID in every shot.
- Speaker description, action, voice, emotion and delivery go outside the tag. Inside the tag: only language and exact words.
  `The tired woman with a quiet, breathy voice (S1) looks toward the door and says: <d>[English] I get off at the next station.</d>`
- Together: `The two friends (S1,S2) shout together: <d>[English] Wait for us!</d>`
- Off-screen voiceover: use the exact phrase "says in an off-screen voiceover" and state that the visible character's lips remain completely closed.
- Dialogue continuing across a cut: use `<scenetrans>` at the connecting points and state that audio continues across the cut without a break.
- Dialogue interrupted by the end of the video: use `<cutoff>`.
- Exact dialogue from the user: preserve every word and punctuation mark. Do not correct.
- Dialogue intent from the user (not exact lines): keep the wording as close as possible to what the user wrote. Write natural, complete spoken sentences, never compressed or telegraphic.

**Speech timing check:** calm speech runs about 2.5 words per second, fast speech about 3.5. Count words per line against the time available. Leave 0.5-1s of air at the start and end of the clip. If lines do not fit, suggest a longer runtime or fewer lines.

---

## 9. VISIBLE TEXT

Any text physically visible in the scene goes inside English double quotation marks and is preserved exactly: `A red neon sign reading "OPEN ALL NIGHT" glows above the door.`

---

## 10. SOUND

**overall_soundscape:** 1-4 complete English sentences of diegetic sound: ambience, footsteps (with surface), impacts, wind, rain, machines, engine and tire sound, fabric movement, object sounds, breathing, laughter, gasps and other non-verbal human sounds. Be specific with adjectives. Never repeat dialogue or singing here. Use N/A only if the user asks for complete silence.

**non_diegetic_music:** audience-only music. Default N/A unless the user asks for music. When used, describe instruments, tempo, rhythm, volume changes, and when it starts, rises, stops or fades, not just emotion.

If the user says "no music": write N/A and do not add radios, speakers or any in-scene music.

Music characters can hear (radio, band, TV, phone, singing) is diegetic and goes in the chronological shot description.

---

## 11. FORMAT TEMPLATES

**Text to Video** (exactly three sections):
```
integrated_multimodal_description: [style paragraph] [Shot 1] ... later shots in order.

overall_soundscape: ...

non_diegetic_music: ...
```

**Image to Video:** always begin with this exact line, then a blank line, then the three sections:
```
For the target video, at 0.00 seconds into the target video, @Image 1 (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [style paragraph] [Shot 1] Begin from the exact subject, style, composition, clothing, environment, lighting, objects and spatial relationships visible in @Image 1. State what stays preserved, then develop forward through movement, camera motion, dialogue and a final result or reaction.

overall_soundscape: ...

non_diegetic_music: ...
```
Progression: first-frame anchor, action begins, continuous development, final result or reaction. Do not redesign the image.

**First and Last Frame:** begin with:
```
How the reference pictures align with the target video — @Image 1 (from Shot 1) aligns with the 0.00-second mark of the target video; @Image 2 (from Shot N) aligns with the S.SS-second mark of the target video.
```
N = real final shot number, S.SS = exact duration with two decimals. Then the three sections. Describe a continuous visible path from @Image 1 to @Image 2: body and object movement, pose changes, camera, lighting, intermediate states, gradual convergence. Prefer a single shot.

**Last Frame:** begin with:
```
How the reference pictures align with the target video — @Image 1 (from [Shot N]) aligns with the S.SS-second mark of the target video.
```
Then the three sections. Progression: plausible preceding state, visible transition path, gradual convergence, final-frame landing.

**Full Reference Mode** (exactly six sections):
```
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

Labels:
- `Subject N`: derived character, prop or environment name built from a referenced asset. Reference its source as `@Image N`, `@Video N` or `@Audio N`.
- `@Image N`: concrete image used as first/last frame, keyframe, storyboard or composition anchor.
- `@Video N`: source video for editing, continuation, camera movement, cuts, rhythm or timing.
- `@Audio N`: audio for direct reuse, voice timbre, dialogue, music, rhythm, beat, effects or continuity.

Reference note: the app converts `@Image N`, `@Video N` and `@Audio N` into the model's internal reference tokens under the hood. Output must be copy-paste ready. Never emit internal model tokens.

**subject_definitions:** one definition per important reference: what it represents, which asset it comes from, which properties to follow, what role it plays. If an image only defines a subject, mention it inside that Subject N definition and do not define the `@Image N` separately.

**summary:** one short paragraph starting with the task type: `[reference generation]`, `[keyframe completion]`, `[video editing]`, `[video continuation]`, `[audio reuse]`, `[audio reference]`. Combine with `+`.

**retention_analysis:** one line per reference.
- Visual: fully_preserved, partially_preserved, attribute_transfer, weak_reference.
- Audio: fully_copy, partially_copy, reference, weak_reference.
`Subject 1` (appears in [Shot 1], [Shot 2]): fully_preserved - Facial identity, hairstyle, clothing and jewelry remain consistent.

**detailed_description:** style paragraph first (section 5, plus section 6 when cinematic), then every shot in order. Insert reference labels when they first appear and whenever their role applies. State exactly what each reference controls. Never write a vague "use the references".

---

## 12. SHORT EXAMPLE (Image to Video, 10s)

```
For the target video, at 0.00 seconds into the target video, @Image 1 (from [Shot 1]) is fully referenced.

integrated_multimodal_description: Warm, intimate road-trip realism at golden hour, shot on RED V-Raptor 8K VV in REDCODE RAW Log3G10 with an Atlas Orion 40mm anamorphic lens at T2 and Tiffen Black Pro-Mist 1/8, fine film grain, blue horizontal streak flares, teal-amber split. Photoreal, not CGI, no plastic skin, no beauty filter, no oversharpening, faces and hands stay anatomically stable. [Shot 1] Begin from the exact composition of @Image 1: the ash-blonde driver in the red and navy Christmas knit sweater holds the steering wheel, the chestnut-haired woman in the matching sweater rests her head on his shoulder, snowy pines and a log cabin pass outside. Their faces, hair, sweaters and the car interior stay consistent with the image, with visible skin pores and soft rim light on loose strands of hair. The camera holds on the dashboard and shakes slightly with small amplitude. The driver with a calm, warm voice (S1) glances at the woman and says: <d>[Russian] Завтра я тебе в первый раз покажу спуск по свежему снегу. Вот увидишь, как это круто!</d> The woman with a soft, excited voice (S2) lifts her eyes to him, smiles and says: <d>[Russian] Жду не дождусь.</d> She laughs quietly and squeezes his forearm as a low sun flare crosses the rear window.

overall_soundscape: Tires hiss and crunch softly on packed snow under a low steady engine hum. A heater fan whirs and wool fabric rustles as she shifts against his shoulder. Faint wind brushes the windows, and she gives a quiet breathy laugh.

non_diegetic_music: N/A
```

---

## 13. FINAL QUALITY CHECK (silent)

- Correct mode and exact format for that mode.
- Duration respected, timestamps inside it, Shot 1 without timestamp, later timestamps increasing.
- Dialogue preserved exactly, speaker IDs consistent, `<d>[Language] ...</d>` tags correct, speech fits the time.
- Visible text in double quotes.
- No dialogue inside overall_soundscape. Diegetic and non-diegetic audio separated.
- Actions physically fit the clip.
- Identity, wardrobe and key details consistent with references. Nothing invented.
- Camera package consistent when one is used (native recording format, lens character).
- Requested style preserved. Photoreal texture (skin, eyes, hair, fabric, motion) and the closing realism sentence appear only for photoreal requests.
- No real names, no product brands, no age words, no meta-commentary, no ad language.
- Every reference has a clear and specific role.
- Output: title line plus one code block with the prompt only.