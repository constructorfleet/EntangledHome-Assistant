# Conversation Sentence Templates

EntangledHome packages default conversation templates for every shipped intent alongside a
catch-all handler that forwards free-form requests to the adapter. The defaults live under
`custom_components/entangledhome/sentences/en` inside the integration directory.

## Override workflow

1. Copy the matching `<intent>.yaml` file into your Home Assistant configuration at
   `config/custom_components/entangledhome/sentences/en/<intent>.yaml`.
2. Restart the integration (or Home Assistant) so it can load override templates first and fall back
   to packaged defaults for intents that are not customized.

The catch-all behavior is always active so overrides can focus on refining the primary intent
sentences without blocking natural-language fallthrough to the adapter.
