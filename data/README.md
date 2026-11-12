# Datos

| Archivo | Qué es |
|---|---|
| `sample_games.csv` | Catálogo **de muestra con 43 juegos FICTICIOS** (nombres, descripciones, precios y reseñas inventados). Sirve para probar el agente sin descargar nada. **No usarlo como datos reales en el informe.** |
| `sample_games.embeddings.npy` / `.json` | Índice de embeddings del catálogo de muestra, generado con el backend `hash` (doble de pruebas sin red; NO es similitud semántica real). Para búsqueda semántica real, regenerarlo con NVIDIA NIM (ver abajo). |
| `catalog.csv` | **Incluido.** Catálogo real procesado (1.000 juegos, revisión `6c21457` del dataset, generado el 2026-11-11). Lo regenera `scripts/prepare_data.py`. Si existe, la aplicación lo usa en lugar del de muestra. |
| `catalog.embeddings.npy` / `.json` | **Incluido.** Índice de embeddings del catálogo real (`nvidia/nemotron-3.5-embed-1b`, 1000 × 2048). Lo regenera `scripts/build_embeddings.py`; se rechaza automáticamente si no coincide con el hash de `catalog.csv`. |
| `catalog_info.json` | **Incluido** (lo crea `prepare_data.py`). Procedencia: dataset, revisión, fecha de consulta, criterios y conteos por paso. |

## Obtener el catálogo real

```bash
pip install -r requirements-data.txt
python scripts/prepare_data.py                     # descarga de Hugging Face → data/catalog.csv
python scripts/prepare_data.py --source train.parquet --tags-csv games.csv   # o desde archivos locales del dataset
python scripts/build_embeddings.py                 # embeddings con NVIDIA NIM (una sola vez)
```

## Esquema del catálogo procesado

`app_id, name, description, genres, tags, price, windows, mac, linux, positive, negative, release_date`

- `genres` y `tags`: listas separadas por `|`.
- `price`: USD, numérico.
- `windows`, `mac`, `linux`: `True` / `False`.
- `description`: `short_description` del dataset (o `detailed_description` sin HTML si la corta es muy breve).

### Correspondencia con el dataset original (FronkonGames/steam-games-dataset)

| Procesado | Original |
|---|---|
| `app_id` | `appID` |
| `name` | `name` |
| `description` | `short_description` / `detailed_description` |
| `genres` | `genres` |
| `tags` | `Tags` de `games.csv` (el `tags` del parquet viene vacío; ver abajo) |
| `price` | `price` |
| `windows`, `mac`, `linux` | `windows`, `mac`, `linux` |
| `positive`, `negative` | `positive`, `negative` |
| `release_date` | `release_date` (normalizada a `AAAA-MM-DD`) |

### Etiquetas

En la versión parquet de Hugging Face, `tags` tiene tipo `List(null)` y está vacía en todas las filas (en
`games.json` las etiquetas son un diccionario `{etiqueta: votos}`). `prepare_data.py` lo detecta, descarga
`games.csv` de la misma revisión y completa las etiquetas por `appID`. Ese CSV tiene la cabecera desalineada
(`DiscountDLC count` corresponde a dos columnas); el script la separa antes de leer. `catalog_info.json`
registra el origen en `tags_source` y cuántos juegos del catálogo tienen etiquetas en `catalogo_con_tags`.

`price` es el precio en la fecha de recolección, con el descuento vigente entonces.

## Atribución y licencia

Fuente: FronkonGames, *Steam Games Dataset*, Hugging Face — https://huggingface.co/datasets/FronkonGames/steam-games-dataset.
Ficha consultada el 2026-11-11 (revisión `6c21457b9ebf0a6a7f5b91e11281d65d456ea30e`): los metadatos declaran
`license: mit`, y el único texto sobre licencias dice *"This dataset has been created with this code (MIT)"*, en
referencia al código de recolección ([Steam-Games-Scraper](https://github.com/FronkonGames/Steam-Games-Scraper)).
La ficha no fija términos adicionales para los datos ni menciona CC-BY. Se conserva la atribución a FronkonGames.
