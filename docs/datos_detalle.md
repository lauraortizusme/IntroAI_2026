# Datos: detalle

Complementa la sección 3 del README y [`data/README.md`](../data/README.md).

**Fuente principal:** [Steam Games Dataset — FronkonGames](https://huggingface.co/datasets/FronkonGames/steam-games-dataset),
publicado en Hugging Face. Se conservará la atribución correspondiente a la fuente.

> **Licencia (ficha consultada el 2026-11-11, revisión `6c21457`).** Los metadatos de la ficha declaran
> `license: mit`. El único texto de la ficha que menciona una licencia es *"This dataset has been created with
> [this code](https://github.com/FronkonGames/Steam-Games-Scraper) (MIT)"*, es decir, MIT se refiere al código
> de recolección; la ficha no establece términos adicionales para los datos ni menciona CC-BY (una versión previa
> de este README indicaba CC-BY-4.0 por error). Los textos e imágenes de las fichas de Steam pertenecen a sus
> respectivos titulares; aquí se usan con fines académicos y se conserva la atribución a FronkonGames.

**Selección del catálogo:** recorte de hasta 1.000 juegos con descripción disponible y en inglés,
priorizando los títulos con mayor número de reseñas (`positive + negative`). Criterios aplicados por
`scripts/prepare_data.py`, que registra en `data/catalog_info.json` la fuente, la revisión del dataset, la
fecha de consulta y los conteos tras cada paso:

1. El título es válido y el precio es numérico y no negativo.
2. El inglés figura entre los idiomas soportados (`supported_languages`).
3. Descripción de al menos 60 caracteres: `short_description` o, si es muy breve, `detailed_description` sin HTML.
4. La descripción está en inglés (heurística: proporción de caracteres ASCII y de palabras funcionales en inglés).
5. Sin duplicados por título (se conserva el de más reseñas).
6. Los N primeros por número de reseñas (N = 1.000 por defecto).

**Campos utilizados** (nombres confirmados contra el visor del dataset; el original tiene 41 columnas en `snake_case`):

| Catálogo procesado | Columna original |
|---|---|
| `app_id` | `appID` |
| `name` | `name` |
| `description` | `short_description` / `detailed_description` |
| `genres` | `genres` (lista; se guarda separada por `\|`) |
| `tags` | `Tags` de `games.csv` (ver nota) |
| `price` | `price` (USD) |
| `windows`, `mac`, `linux` | `windows`, `mac`, `linux` |
| `positive`, `negative` | `positive`, `negative` |
| `release_date` | `release_date` (normalizada a `AAAA-MM-DD`) |

**Preparación de datos:**

1. Descargar el conjunto de datos y documentar su versión o fecha de consulta (`prepare_data.py` lo hace).
2. Seleccionar los registros según el criterio definido.
3. Normalizar los tipos de datos, especialmente el precio y las listas de géneros y etiquetas.
4. Eliminar duplicados y registros sin descripción.
5. Guardar el catálogo procesado (`data/catalog.csv`).
6. Generar una sola vez los embeddings de las descripciones y almacenarlos para reutilizarlos (`build_embeddings.py`).

**Nota sobre las etiquetas.** En la versión parquet del dataset (la que carga `datasets`), la columna `tags`
llega vacía en las 124.146 filas: en `games.json` las etiquetas son un diccionario `{etiqueta: votos}` que no
sobrevivió a la conversión. `prepare_data.py` lo detecta y completa las etiquetas por `appID` desde `games.csv`
de la misma revisión, corrigiendo su cabecera desalineada (`DiscountDLC count` fusiona dos columnas: 39 nombres
para 40 valores). Se verificó que las etiquetas, el precio y la compatibilidad con macOS de los 1.000 juegos del
catálogo coinciden con `games.csv`.

**Conteos reales** (ejecución del 2026-11-11, `data/catalog_info.json`): 124.146 registros → 124.145 con título
y precio válido → 110.602 con inglés soportado → 110.527 con descripción → 109.046 con descripción en inglés →
107.262 sin duplicados → **1.000** en el catálogo (todos con etiquetas). 152 de ellos tienen precio 0.

El catálogo es una captura fija: los precios y demás datos pueden no coincidir con los disponibles actualmente
en Steam. El precio es el que figuraba en la fecha de recolección, **incluido el descuento vigente** en ese
momento (p. ej., Stardew Valley aparece a 8,99 USD con un 40 % de descuento). Algunos valores de la fuente
llaman la atención y no se corrigieron (p. ej., *Grand Theft Auto V Legacy* figura con precio 0).

**Catálogo de muestra.** El repositorio incluye `data/sample_games.csv`, con **43 juegos ficticios** y el mismo
esquema, para probar el sistema sin descargar nada. Sus datos son inventados y no deben presentarse como resultados
reales. Si existe `data/catalog.csv`, la aplicación lo usa en su lugar; el repositorio **ya incluye** el catálogo real
procesado y su índice de embeddings, de modo que no hace falta regenerarlos para usar la aplicación.

[← Volver al README](../README.md)
