# SayMy brand (v0.1)

**Idea:** a speech bubble holding a rising sun. The rays are also sound waves. *Say it. Done.*
**Story:** Born in Africa. Built for the world.

## Colour (design/tokens/tokens.json)
| Name | Hex | Use |
|---|---|---|
| Lake Night | #0C1A2A | base background |
| Deep Water | #14283C | panels, windows |
| Water Light | #1E3A55 | hover, borders |
| Bark Cloth | #F3E9D8 | primary text |
| Mist | #9FB3C8 | secondary text |
| Sunrise | #FF8A1F | main accent, focus |
| Savanna Gold | #F5B93A | highlights, clock |
| Banana Leaf | #3FA66B | success, charging |
| Lake Blue | #2F8FD1 | information |
| Hibiscus | #E0445B | errors, critical |

## Type
Inter for the interface, JetBrains Mono for code, Noto as the fallback so every script renders.

## Pattern
Nested diamonds with a dotted centre (bark-cloth inspired), used as a quiet band at the foot of
wallpapers and boot screens. Never full-screen, never loud.

## Time of day
Four wallpapers (sunrise, day, dusk, night) switch with the local hour. The accent colour recorded in
`~/.cache/saymy/accent` shifts with them; wiring it into the panel is a Stage 2 task.

## Voice
Plain verbs, sentence case, no jargon. Errors say what happened and what to do, and never apologise.
An empty screen invites an action. Same name for an action everywhere.

## Naming
SayMy Shell, Say Bar, SayMy Sky, SayMy Share, SayMy Packs, SayMy Store.
Check trademark availability of "SayMy" in your target markets before the brand grows.

## Regenerate the art
`python3 design/generate_assets.py` (needs `librsvg2-bin` and ImageMagick).
