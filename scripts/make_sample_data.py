"""Genera data/sample_games.csv: un catálogo SINTÉTICO para probar el agente sin descargar Steam.

Todos los juegos, descripciones, precios y reseñas son inventados. Tienen el mismo
esquema que el catálogo procesado por scripts/prepare_data.py, de modo que el resto
del código no distingue entre uno y otro. No usar como datos reales en el informe.

Uso:
    python scripts/make_sample_data.py
"""
from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_games.csv"
COLUMNS = [
    "app_id", "name", "description", "genres", "tags", "price",
    "windows", "mac", "linux", "positive", "negative", "release_date",
]

# (nombre, descripción, géneros, etiquetas, precio USD, plataformas W/M/L, positivas, negativas, fecha)
GAMES = [
    # --- Granja / relajante ---
    ("Willowbrook Farm",
     "A cozy farming simulator where you plant crops, raise animals and befriend the villagers of a sleepy countryside town at your own relaxed pace.",
     "Simulation|Casual|Indie", "Farming Sim|Relaxing|Cozy|Singleplayer|Pixel Graphics|Life Sim", 14.99, "WML", 18200, 900, "2021-03-12"),
    ("Turnip Hollow",
     "Run a relaxing farm together with up to four friends. Share the chores, grow vegetables, decorate the barn and enjoy a calm online co-op farming adventure.",
     "Simulation|Casual|Indie", "Farming Sim|Relaxing|Co-op|Online Co-op|Multiplayer|Cozy", 9.99, "WM", 7600, 650, "2022-06-02"),
    ("Sunpatch Valley",
     "Rebuild an abandoned valley farm, expand the town and grow your harvest in this peaceful farming and town-building game with gentle seasons.",
     "Simulation|Strategy|Indie", "Farming Sim|Relaxing|Building|Singleplayer|Cute", 12.49, "W", 4300, 410, "2020-09-18"),
    ("Little Orchard Days",
     "A peaceful orchard keeping game: prune trees, make jam, sell fruit at the market and relax with a soothing soundtrack and no time pressure.",
     "Casual|Simulation|Indie", "Relaxing|Farming Sim|Cozy|Singleplayer|Atmospheric", 7.99, "WML", 2900, 180, "2023-04-21"),
    ("Pasture & Pie",
     "Farm fresh ingredients and bake pies for the whole village. Couch co-op for two players makes this cooking and farming sim a warm game to play with a friend.",
     "Simulation|Casual", "Farming Sim|Cooking|Local Co-op|Co-op|Relaxing|Cute", 11.99, "WM", 3100, 350, "2022-10-07"),
    ("Beehive Buddies",
     "Keep a colony of bees, collect honey and decorate your meadow with friends in a casual, relaxing co-op game that anyone can pick up in minutes.",
     "Casual|Simulation|Indie", "Relaxing|Co-op|Online Co-op|Multiplayer|Cute|Cozy", 5.99, "WML", 5200, 280, "2023-08-15"),
    # --- Relajante / otros ---
    ("Paper Lantern Garden",
     "A zen gardening puzzle game. Arrange stones, plants and lanterns to create calm gardens, with soft music and no fail states.",
     "Casual|Indie", "Relaxing|Puzzle|Zen|Singleplayer|Minimalist|Atmospheric", 4.99, "WML", 6100, 240, "2019-05-30"),
    ("Quiet Harbor",
     "A chill fishing game set in a misty harbor town. Cast your line, collect rare fish and chat with locals while the day slowly passes.",
     "Casual|Simulation|Indie", "Relaxing|Fishing|Cozy|Singleplayer|Atmospheric", 6.99, "WM", 4700, 390, "2021-11-04"),
    ("Moss & Mist",
     "Hike through foggy forests and mountain trails in a peaceful exploration game about slowing down and enjoying the scenery.",
     "Adventure|Indie", "Relaxing|Exploration|Atmospheric|Singleplayer|Walking Simulator|Nature", 11.99, "WM", 5400, 520, "2022-02-24"),
    ("Bookshop Nights",
     "Open a tiny bookshop after dark. Recommend stories to quirky customers, arrange shelves and drink tea in this cozy management game.",
     "Simulation|Casual|Indie", "Cozy|Relaxing|Management|Singleplayer|Story Rich|Cute", 13.99, "WM", 3900, 260, "2023-01-19"),
    ("Cloud Cartographer",
     "Sail between floating islands and draw maps of the sky. A relaxing exploration game with a gentle story and painterly visuals.",
     "Adventure|Indie", "Exploration|Relaxing|Atmospheric|Singleplayer|Beautiful|Open World", 9.49, "W", 2200, 190, "2020-07-08"),
    ("Campfire Tales Co-op",
     "Gather around the campfire with friends and tell cooperative stories in this relaxing party game full of laughter, drawing and silly prompts.",
     "Casual|Indie", "Co-op|Multiplayer|Party Game|Relaxing|Local Multiplayer|Funny", 8.99, "WM", 2600, 310, "2022-09-09"),
    ("Sandcastle Architects",
     "A free relaxing sandbox where you build giant sandcastles, share creations with friends and enjoy a calm beach atmosphere.",
     "Casual|Simulation|Free To Play", "Relaxing|Sandbox|Building|Free to Play|Multiplayer|Cozy", 0.0, "WML", 8800, 1700, "2021-06-25"),
    ("Cafe Cosmos",
     "Run a cozy space cafe, brew galactic coffee and decorate your station. A charming management game that is easy to relax with.",
     "Simulation|Casual|Indie", "Cozy|Management|Relaxing|Singleplayer|Cute|Space", 10.99, "WM", 3300, 270, "2023-05-11"),
    ("Tiny Colony",
     "Guide a small community of settlers in a relaxing colony builder where you set priorities, gather resources and watch your village grow.",
     "Strategy|Simulation|Indie", "City Builder|Relaxing|Colony Sim|Singleplayer|Building|Cute", 14.99, "WM", 3700, 460, "2021-08-27"),
    # --- Shooters ---
    ("Ashfall Squad",
     "Team up with up to three friends in a fast cooperative shooter and survive waves of zombies in ruined cities with upgradeable weapons.",
     "Action", "Shooter|Co-op|Online Co-op|FPS|Zombies|Multiplayer", 7.99, "WL", 15400, 3100, "2020-10-30"),
    ("Neon Breach",
     "A fast-paced cyberpunk first person shooter with a story campaign, hacking abilities and neon-drenched arenas.",
     "Action", "FPS|Shooter|Cyberpunk|Singleplayer|Fast-Paced|Sci-fi", 19.99, "W", 9800, 2400, "2022-03-17"),
    ("Rustline Raiders",
     "Four-player cooperative third-person shooter set in a post-apocalyptic wasteland. Loot, upgrade your vehicle and defend your camp together.",
     "Action|Adventure", "Shooter|Co-op|Online Co-op|Third Person Shooter|Post-apocalyptic|Multiplayer", 9.49, "W", 6900, 1200, "2021-12-03"),
    ("Bunker Zero",
     "Hold the bunker with a friend in a cooperative horde shooter for two to four players, with tight gunplay and scary night waves.",
     "Action|Indie", "Shooter|Co-op|Online Co-op|Horde|Multiplayer|Survival", 4.99, "WL", 4100, 760, "2019-11-22"),
    ("Orbital Strike Arena",
     "A free-to-play competitive team shooter with short matches, class abilities and ranked seasons set on orbital stations.",
     "Action|Free To Play", "Shooter|FPS|Multiplayer|Competitive|Free to Play|Team-Based", 0.0, "W", 52000, 14000, "2020-04-14"),
    ("Pixel Gunners",
     "A retro top-down shooter where two players can team up in couch co-op, blasting robots through colorful pixel art levels.",
     "Action|Indie", "Shooter|Co-op|Local Co-op|Pixel Graphics|Top-Down Shooter|Retro", 6.99, "WML", 3800, 350, "2022-07-29"),
    # --- Estrategia ---
    ("Iron Frontier Tactics",
     "A turn-based tactics game about leading a small squad through a frontier war, with deep positioning and permanent consequences.",
     "Strategy|RPG", "Turn-Based Tactics|Strategy|Singleplayer|Difficult|War", 24.99, "WML", 8700, 1100, "2019-09-05"),
    ("Kingdom of Embers",
     "A grand strategy game of diplomacy and conquest in a medieval fantasy world, with deep economy and shifting alliances.",
     "Strategy", "Grand Strategy|Strategy|Fantasy|Singleplayer|Multiplayer|Medieval", 29.99, "WL", 12300, 2900, "2021-02-11"),
    ("Hexa Wars",
     "A quick hex-based board strategy game for one or two players. Easy to learn, hard to master and perfect for short sessions.",
     "Strategy|Casual|Indie", "Strategy|Board Game|Turn-Based|Local Multiplayer|Minimalist", 4.99, "WML", 1800, 220, "2020-01-20"),
    # --- RPG ---
    ("Ember Saga",
     "A sprawling fantasy RPG with a branching story, party-based combat and hundreds of quests across a hand-painted continent.",
     "RPG|Adventure", "RPG|Fantasy|Story Rich|Singleplayer|Open World|Party-Based RPG", 29.99, "WM", 21000, 3200, "2020-11-12"),
    ("Crypt of Echoes",
     "A roguelike dungeon crawler where every run is different. Choose a hero, collect relics and fight through haunted crypts.",
     "RPG|Action|Indie", "Roguelike|Dungeon Crawler|Action RPG|Singleplayer|Difficult|Replay Value", 12.99, "WML", 9400, 1300, "2021-09-30"),
    ("Nova Drifters",
     "A space RPG about a crew of drifters trading, fighting and exploring a vast galaxy full of strange factions and ancient ruins.",
     "RPG|Adventure", "Space|RPG|Sci-fi|Exploration|Story Rich|Singleplayer", 22.99, "W", 7200, 1900, "2022-05-05"),
    # --- Carreras / deportes ---
    ("Redline Rally",
     "A fast arcade rally racing game with dozens of cars, dirt tracks and online time-attack challenges.",
     "Racing|Sports", "Racing|Driving|Multiplayer|Arcade|Fast-Paced", 14.99, "W", 5100, 1400, "2020-06-19"),
    ("Pocket Kicks",
     "Arcade soccer for local multiplayer with chaotic power-ups, short matches and a mode for up to four players on one screen.",
     "Sports|Casual|Indie", "Sports|Local Multiplayer|Arcade|Funny|Co-op|Party Game", 9.99, "WML", 4200, 600, "2021-04-16"),
    ("Wave Rider Surf",
     "A laid-back surfing game with calm waves, tricks and sunset sessions. Easy controls make it a relaxing sports game.",
     "Sports|Casual|Indie", "Sports|Relaxing|Singleplayer|Beautiful|Arcade", 7.99, "WM", 1500, 210, "2022-08-12"),
    # --- Puzles / plataformas ---
    ("Gloomy Glow",
     "An atmospheric puzzle platformer about a tiny light spirit exploring dark caves, with clever light-and-shadow puzzles.",
     "Adventure|Indie", "Puzzle Platformer|Atmospheric|Singleplayer|Puzzle|Beautiful|Short", 8.99, "WML", 6500, 520, "2019-10-10"),
    ("Block Garden",
     "A minimalist block-sliding puzzle game with hundreds of handcrafted levels and a soothing soundtrack.",
     "Casual|Indie", "Puzzle|Relaxing|Minimalist|Singleplayer|Casual", 2.99, "WML", 3000, 150, "2018-12-06"),
    ("Echo Chamber Puzzles",
     "Solve sound-based puzzles in a series of echoing rooms. A short, clever puzzle adventure for patient players.",
     "Adventure|Indie", "Puzzle|Atmospheric|Singleplayer|Short|Mystery", 3.99, "WM", 1200, 130, "2020-03-03"),
    # --- Terror / aventura ---
    ("Hollow Corridors",
     "A psychological horror game set in an abandoned hospital. Hide, listen and survive as something follows you through the dark.",
     "Action|Adventure|Indie", "Horror|Psychological Horror|Atmospheric|Singleplayer|Scary|Survival Horror", 11.99, "W", 8200, 1600, "2021-10-29"),
    ("The Last Signal",
     "A survival horror game on a remote arctic station, where you must keep the radio alive while an unknown presence hunts you.",
     "Action|Adventure", "Horror|Survival Horror|Atmospheric|Singleplayer|Sci-fi|Scary", 15.99, "WL", 5600, 1500, "2022-10-14"),
    ("Skyward Isles",
     "A colorful adventure across floating islands. Glide, solve puzzles and uncover the mystery of the sunken sky kingdom.",
     "Adventure", "Adventure|Exploration|Open World|Colorful|Singleplayer|Fantasy", 17.99, "WM", 6300, 700, "2022-04-08"),
    ("Case of the Missing Clockmaker",
     "A mystery adventure in a snowy clock town. Interrogate suspects, collect clues and piece together the clockmaker's last night.",
     "Adventure|Indie", "Mystery|Detective|Story Rich|Singleplayer|Point & Click|Atmospheric", 12.49, "WML", 3400, 320, "2020-12-02"),
    # --- Gestión / otros cooperativos ---
    ("Rail Baron Tycoon",
     "Build a railway empire, manage routes and outsmart rival companies in this classic transport tycoon.",
     "Simulation|Strategy", "Management|Tycoon|Trains|Singleplayer|Economy|Building", 19.99, "WL", 4800, 900, "2019-06-14"),
    ("Cityline Planner",
     "Plan and manage a modern city with detailed zoning, traffic and budgets in this deep city builder.",
     "Simulation|Strategy", "City Builder|Management|Singleplayer|Building|Economy", 24.99, "WM", 9100, 2600, "2021-05-20"),
    ("Dungeon Buddies",
     "A four-player co-op dungeon brawler. Pick a class, smash monsters and share loot with friends in colorful procedural dungeons.",
     "Action|RPG|Indie", "Co-op|Online Co-op|Dungeon Crawler|Multiplayer|Action RPG|Funny", 11.99, "WML", 7700, 1000, "2022-01-14"),
    ("Kitchen Chaos Crew",
     "Chaotic cooperative cooking for up to four players. Chop, fry and deliver orders in kitchens that keep changing around you.",
     "Casual|Simulation", "Co-op|Local Co-op|Online Co-op|Cooking|Party Game|Funny|Multiplayer", 14.99, "WM", 10400, 1900, "2021-07-23"),
    ("Brawl Street Legends",
     "A 2D arcade fighting game with a roster of street legends, combo systems and fast local or online versus matches.",
     "Action", "Fighting|Multiplayer|Local Multiplayer|Arcade|Competitive|2D", 19.99, "W", 4600, 1100, "2020-08-21"),
    ("Stellar Idle Miner",
     "A free idle game about mining asteroids. Upgrade your drills, hire robots and watch your space empire grow while you relax.",
     "Casual|Simulation|Free To Play", "Idle|Free to Play|Relaxing|Singleplayer|Space|Clicker", 0.0, "WM", 3600, 900, "2019-03-28"),
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for i, (name, desc, genres, tags, price, plat, pos, neg, date) in enumerate(GAMES, start=1):
            writer.writerow([
                900000 + i, name, desc, genres, tags, f"{price:.2f}",
                "W" in plat, "M" in plat, "L" in plat, pos, neg, date,
            ])
    print(f"Catálogo de muestra con {len(GAMES)} juegos ficticios → {OUT}")


if __name__ == "__main__":
    main()
