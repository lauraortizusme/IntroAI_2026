"""Pruebas de la preparación de datos con un archivo CRUDO sintético que imita el esquema real
de FronkonGames/steam-games-dataset (41 columnas en snake_case, verificadas en la ficha)."""
from __future__ import annotations

import pandas as pd
import pytest

import prepare_data as prep
from catalog import Catalog

EN = "A relaxing adventure where you explore the world and meet the people of a small town with your friends."
ES = "Un juego de aventuras muy relajante donde exploras el mundo y conoces a la gente de un pueblo pequeño con tus amigos."

RAW_COLUMNS_41 = [
    "appID", "name", "release_date", "estimated_owners", "peak_ccu", "required_age", "price", "dlc_count",
    "detailed_description", "short_description", "supported_languages", "full_audio_languages", "reviews",
    "header_image", "website", "support_url", "support_email", "windows", "mac", "linux", "metacritic_score",
    "metacritic_url", "user_score", "positive", "negative", "score_rank", "achievements", "recommendations",
    "notes", "average_playtime_forever", "average_playtime_2weeks", "median_playtime_forever",
    "median_playtime_2weeks", "developers", "publishers", "categories", "genres", "tags", "screenshots",
    "movies", "packages",
]


def raw_frame(rows: list[dict]) -> pd.DataFrame:
    base = {c: None for c in RAW_COLUMNS_41}
    return pd.DataFrame([{**base, **r} for r in rows], columns=RAW_COLUMNS_41)


def game(i, **kw):
    row = dict(
        appID=i, name=f"Game {i}", release_date="Oct 19, 2023", price=9.99, short_description=EN,
        detailed_description=f"<p>{EN}</p>", supported_languages="['English', 'Spanish - Spain']",
        windows=True, mac=False, linux=False, positive=100 + i, negative=10, genres="Indie,Strategy",
        tags="Single-player,Family Sharing",
    )
    row.update(kw)
    return row


def test_seleccion_aplica_cada_criterio():
    raw = raw_frame([
        game(1),                                                           # válido
        game(2, supported_languages="['French']"),                         # sin inglés
        game(3, short_description=ES, detailed_description=ES),            # descripción en español
        game(4, short_description="", detailed_description=""),           # sin descripción
        game(5, price=-1),                                                 # precio inválido
        game(6, name="game 1", positive=5),                                # duplicado menos popular
        game(7, name=""),                                                  # sin título
        game(8, short_description="Short.", detailed_description=f"<b>{EN}</b> &amp; more"),  # usa la detallada
    ])
    out, stats = prep.select_catalog(raw, n=100)
    assert set(out["name"]) == {"Game 1", "Game 8"}
    assert stats["registros_originales"] == 8 and stats["catalogo_final"] == 2
    assert "<" not in out.loc[out["name"] == "Game 8", "description"].iloc[0]
    assert "&amp;" not in out["description"].iloc[0]


def test_prioriza_resenas_y_respeta_n_y_duplicados():
    raw = raw_frame([game(i, positive=i * 10, negative=0) for i in range(1, 8)] + [game(99, name="GAME 3", positive=1)])
    out, _ = prep.select_catalog(raw, n=3)
    assert out["name"].tolist() == ["Game 7", "Game 6", "Game 5"]
    full, _ = prep.select_catalog(raw, n=100)
    assert full["name"].str.lower().is_unique  # 'GAME 3' no se repite


def test_salida_cumple_el_esquema_y_se_carga_con_catalog(tmp_path):
    raw = raw_frame([
        game(1, genres="Action, RPG", tags="Co-op,Shooter", mac=True, windows="True", linux="False"),
        game(2, genres=["Indie", "Casual"], tags=["Relaxing"], price="4.5", release_date="2020-01-02"),
    ])
    out, _ = prep.select_catalog(raw)
    path = tmp_path / "catalog.csv"
    out.to_csv(path, index=False)
    cat = Catalog.load(path)
    assert len(cat) == 2
    g1 = cat.find_by_name("Game 1")
    assert g1["genres"] == ["Action", "RPG"] and g1["tags"] == ["Co-op", "Shooter"]
    assert bool(g1["mac"]) and bool(g1["windows"]) and not bool(g1["linux"])
    g2 = cat.find_by_name("Game 2")
    assert g2["genres"] == ["Indie", "Casual"] and g2["price"] == 4.5 and g2["release_date"] == "2020-01-02"
    assert cat.find_by_name("Game 1")["release_date"] == "2023-10-19"


def test_lee_csv_y_parquet_con_listas(tmp_path):
    csv, pq = tmp_path / "raw.csv", tmp_path / "raw.parquet"
    # CSV: géneros y etiquetas como texto separado por comas
    raw_frame([game(1), game(2, genres="Indie, Casual", tags="A,B")]).to_csv(csv, index=False)
    # Parquet: géneros y etiquetas como listas (todas las filas del mismo tipo)
    raw_frame([game(1, genres=["Indie", "Strategy"], tags=["X"]),
               game(2, genres=["Indie", "Casual"], tags=["A", "B"])]).to_parquet(pq)
    for src in (csv, pq):
        df, info = prep.load_raw(src)
        out, _ = prep.select_catalog(df)
        assert len(out) == 2 and info["origin"].startswith("archivo local")
        assert out["genres"].str.contains("Indie", regex=False).all() and "|" in out["genres"].iloc[0]


def test_detecta_columnas_desalineadas_y_faltantes():
    malo = raw_frame([game(i, price="Windows") for i in range(10)])
    with pytest.raises(ValueError, match="desalineadas"):
        prep.select_catalog(malo)
    with pytest.raises(ValueError, match="faltan columnas"):
        prep.select_catalog(raw_frame([game(1)]).drop(columns=["short_description"]))


def test_heuristica_de_idioma():
    assert prep.looks_english(EN) and not prep.looks_english(ES)
    assert not prep.looks_english("这是一个非常有趣的游戏，你可以和朋友们一起玩，探索世界，建造城市，非常好玩。")
    assert not prep.looks_english("Short text")


# --- Etiquetas: el parquet de Hugging Face trae `tags` vacía (List(null)) en TODAS las filas;
# games.csv sí las trae, pero con la cabecera fusionada "DiscountDLC count" (39 nombres, 40 valores).
GAMES_CSV_HEADER = (
    "AppID,Name,Release date,Estimated owners,Peak CCU,Required age,Price,DiscountDLC count,About the game,"
    "Supported languages,Full audio languages,Reviews,Header image,Website,Support url,Support email,Windows,Mac,"
    "Linux,Metacritic score,Metacritic url,User score,Positive,Negative,Score rank,Achievements,Recommendations,"
    "Notes,Average playtime forever,Average playtime two weeks,Median playtime forever,Median playtime two weeks,"
    "Developers,Publishers,Categories,Genres,Tags,Screenshots,Movies"
)


def games_csv_row(app_id, name, categories, genres, tags):
    # 40 valores: Price=5.24, Discount=65, DLC count=0 (la fila real de 'Supipara' en games.csv)
    vals = [str(app_id), f'"{name}"', '"Aug 1, 2023"', '"0 - 20000"', "0", "0", "5.24", "65", "0",
            '"About, with commas"', "\"['English']\"", '"[]"', '""', '""', '""', '""', '""', "True", "False",
            "False", "0", '""', "0", "252", "11", '""', "0", "0", '""', "0", "0", "0", "0", '"Dev"', '"Pub"',
            f'"{categories}"', f'"{genres}"', f'"{tags}"', '"shot.jpg"', '""']
    assert len(vals) == 40
    return ",".join(vals)


def test_cabecera_fusionada_de_games_csv():
    header = GAMES_CSV_HEADER.split(",")
    assert len(header) == 39
    fixed = prep.fixed_csv_header(header)
    assert len(fixed) == 40 and fixed[6:9] == ["Price", "Discount", "DLC count"] and fixed[37] == "Tags"
    assert prep.fixed_csv_header(fixed) == fixed  # idempotente


def test_lee_tags_de_games_csv_sin_desalinear(tmp_path):
    path = tmp_path / "games.csv"
    path.write_text("\n".join([
        GAMES_CSV_HEADER,
        games_csv_row(496350, "Supipara - Chapter 1 Spring Has Come!", "Single-player,Steam Cloud", "Adventure",
                      "Adventure,Visual Novel,Anime,Cute"),
        games_csv_row(10, "Sin etiquetas", "Single-player", "Action", ""),
    ]) + "\n", encoding="utf-8")
    tags = prep.read_tags_from_games_csv(path)
    # Sin corregir la cabecera, 'Tags' apuntaría a la columna de géneros ('Adventure').
    assert tags.loc[496350] == "Adventure,Visual Novel,Anime,Cute"
    assert tags.loc[10] == ""


def test_completa_tags_vacias_del_parquet_por_appid(tmp_path):
    raw = raw_frame([game(1, tags=[]), game(2, tags=[]), game(3, tags=["Ya tenía"])])
    assert not prep.tags_all_empty(raw["tags"])
    assert prep.tags_all_empty(raw_frame([game(1, tags=[]), game(2, tags=None)])["tags"])
    filled, n = prep.fill_tags(raw, pd.Series({1: "Co-op,Shooter", 3: "Otra", 99: "X"}))
    assert n == 1  # solo la fila 1: la 2 no está en el CSV y la 3 ya tenía etiquetas
    out, stats = prep.select_catalog(filled)
    by = {r["name"]: r["tags"] for _, r in out.iterrows()}
    assert by == {"Game 1": "Co-op|Shooter", "Game 2": "", "Game 3": "Ya tenía"}
    assert stats["catalogo_con_tags"] == 2


def test_to_list_conserva_apostrofos_de_las_etiquetas():
    # Error real observado: "Beat 'em up" (Street Fighter V) quedaba como "Beat em up".
    assert prep.to_list("Fighting,Beat 'em up,Shoot 'Em Up") == ["Fighting", "Beat 'em up", "Shoot 'Em Up"]
    assert prep.to_list("['Co-op', \"Beat 'em up\"]") == ["Co-op", "Beat 'em up"]
    assert prep.to_list("[Indie, Casual]") == ["Indie", "Casual"]  # lista sin comillas: respaldo
    assert prep.to_list("[]") == [] and prep.to_list("") == [] and prep.to_list(None) == []


def test_fuente_local_con_tags_vacias_usa_tags_csv_o_avisa(tmp_path, capsys):
    pq = tmp_path / "train.parquet"
    raw_frame([game(496350, tags=[]), game(2, tags=[])]).to_parquet(pq)
    csv = tmp_path / "games.csv"
    csv.write_text(GAMES_CSV_HEADER + "\n" + games_csv_row(496350, "Game", "Single-player", "Adventure",
                                                           "Adventure,Visual Novel") + "\n", encoding="utf-8")
    df, info = prep.load_raw(pq, tags_csv=csv)
    out, stats = prep.select_catalog(df)
    assert out.set_index("app_id").loc[496350, "tags"] == "Adventure|Visual Novel"
    assert stats["catalogo_con_tags"] == 1 and "games.csv" in info["tags_source"]
    _, info = prep.load_raw(pq)  # sin --tags-csv: no falla, pero avisa y lo registra
    assert "vacía" in info["tags_source"] and "AVISO" in capsys.readouterr().out
