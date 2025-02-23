import re
import sqlite3
import json
import random
import os
import requests
import openai

# Set your OpenAI API key.
openai.api_key = os.getenv("OPENAI_API_KEY") or "testkey"

DEFAULT_DECK_SIZE = 60
DB_FILENAME = os.path.abspath("C:/Users/pando/OneDrive/Desktop/MTG Deck Builder/Backend/allprintings.sqlite")

# ----------------------
# Partner Commander Handling Module
# ----------------------

def check_partner_compatibility(commander1, commander2):
    """
    Checks if two commanders can be partnered together.
    Returns (bool, str) tuple: (is_compatible, reason)
    """
    if not commander1 or not commander2:
        return False, "Missing commander data"

    # Get oracle texts
    text1 = commander1.get('oracle_text', '').lower()
    text2 = commander2.get('oracle_text', '').lower()
    name1 = commander1.get('name', '')
    name2 = commander2.get('name', '')

    # Check for basic partner keyword
    has_partner1 = 'partner' in text1
    has_partner2 = 'partner' in text2

    if not (has_partner1 and has_partner2):
        return False, "One or both commanders lack Partner ability"

    # Check for "Partner With" specific pairing
    partner_with1 = None
    partner_with2 = None
    
    # Extract specific partner name if "partner with" is present
    if 'partner with' in text1:
        start_idx = text1.find('partner with') + len('partner with')
        end_idx = text1.find('\n', start_idx) if '\n' in text1[start_idx:] else len(text1)
        partner_with1 = text1[start_idx:end_idx].strip()

    if 'partner with' in text2:
        start_idx = text2.find('partner with') + len('partner with')
        end_idx = text2.find('\n', start_idx) if '\n' in text2[start_idx:] else len(text2)
        partner_with2 = text2[start_idx:end_idx].strip()

    # If either has "Partner With", check specific pairing
    if partner_with1 or partner_with2:
        if partner_with1 and name2.lower() != partner_with1.lower():
            return False, f"{name1} can only partner with {partner_with1}"
        if partner_with2 and name1.lower() != partner_with2.lower():
            return False, f"{name2} can only partner with {partner_with2}"
    
    # If we get here, either both have generic Partner or they're valid Partner With pairs
    return True, "Compatible partners"

def combine_commander_colors(commander1, commander2):
    """
    Combines color identities of both commanders.
    """
    colors1 = set(commander1.get('color_identity', []))
    colors2 = set(commander2.get('color_identity', []))
    return list(colors1.union(colors2))

def analyze_partner_synergy(commander1, commander2):
    """
    Analyzes synergy between partner commanders.
    Returns a synergy score and relevant strategy notes.
    """
    synergy_score = 0
    strategy_notes = []
    
    # Get text and types
    text1 = commander1.get('oracle_text', '').lower()
    text2 = commander2.get('oracle_text', '').lower()
    type1 = commander1.get('type_line', '').lower()
    type2 = commander2.get('type_line', '').lower()

    # Check for tribal synergies
    creature_types1 = set(re.findall(r'([A-Za-z]+) creature', type1))
    creature_types2 = set(re.findall(r'([A-Za-z]+) creature', type2))
    shared_tribes = creature_types1.intersection(creature_types2)
    if shared_tribes:
        synergy_score += 20
        strategy_notes.append(f"Tribal synergy: {', '.join(shared_tribes)}")

    # Check for mechanical synergies
    keywords = ['sacrifice', 'token', 'counter', 'draw', 'combat']
    for keyword in keywords:
        if keyword in text1 and keyword in text2:
            synergy_score += 15
            strategy_notes.append(f"Shared {keyword} mechanic")

    # Check for complementary abilities
    if ('create' in text1 and 'sacrifice' in text2) or ('sacrifice' in text1 and 'create' in text2):
        synergy_score += 25
        strategy_notes.append("Complementary token/sacrifice strategy")

    # Color identity synergy
    colors1 = set(commander1.get('color_identity', []))
    colors2 = set(commander2.get('color_identity', []))
    color_overlap = len(colors1.intersection(colors2))
    synergy_score += color_overlap * 10

    return {
        'score': min(synergy_score, 100),  # Cap at 100
        'notes': strategy_notes,
        'combined_colors': list(colors1.union(colors2))
    }

def get_partner_strategy_emphasis(commander1, commander2):
    """
    Determines which commander should be the primary focus for strategy detection.
    Returns tuple of (primary_commander, secondary_commander, strategy_notes)
    """
    text1 = commander1.get('oracle_text', '').lower()
    text2 = commander2.get('oracle_text', '').lower()
    
    # Score each commander's strategic clarity
    score1 = 0
    score2 = 0
    
    # Keywords that indicate strong strategic direction
    strategy_keywords = {
        'whenever': 3,
        'at the beginning of': 2,
        'at end of': 2,
        'you may': 1,
        'create': 2,
        'draw': 2,
        'sacrifice': 2,
        'counter': 2,
        'combat': 2
    }
    
    for keyword, value in strategy_keywords.items():
        score1 += text1.count(keyword) * value
        score2 += text2.count(keyword) * value
    
    # Consider mana cost as a tiebreaker
    cmc1 = float(commander1.get('cmc', 0))
    cmc2 = float(commander2.get('cmc', 0))
    
    # Lower CMC commander gets a small bonus (easier to cast repeatedly)
    if cmc1 < cmc2:
        score1 += 1
    elif cmc2 < cmc1:
        score2 += 1
    
    # Determine primary and secondary commanders
    if score1 >= score2:
        return (commander1, commander2, f"{commander1.get('name')} appears to be the primary strategic driver")
    else:
        return (commander2, commander1, f"{commander2.get('name')} appears to be the primary strategic driver")

# ----------------------
# Card Line Parsing Module
# ----------------------
def parse_card_line(line):
    """
    Parses a card entry line.
    Handles both complex format: "2x Card Name (SET)"
    and simple format: "Card Name"
    """
    line = line.strip()
    if not line:
        return None, 0
        
    # Try complex format first
    pattern = r"^\s*(?:(\d+)x\s+)?([^(*]+)"
    match = re.match(pattern, line)
    if match:
        count_str = match.group(1)
        count = int(count_str) if count_str else 1
        card_name = match.group(2).strip()
        return card_name, count
        
    # If no match, treat the whole line as a card name
    return line, 1

# ----------------------
# Input Handling Module
# ----------------------
def read_card_list(file_path):
    """
    Reads the card list from a text file and returns a list of card names.
    Now handles both complex and simple card name formats.
    """
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        return []
        
    cards_expanded = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                name, count = parse_card_line(line)
                if name:
                    cards_expanded.extend([name] * count)
                    
        print(f"Successfully read {len(cards_expanded)} cards from file")
        return cards_expanded
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        return []

# ----------------------
# Data Retrieval Module (SQLite with Fallback)
# ----------------------
def fetch_card_data(card_name, conn):
    """
    Fetches card details from the local SQLite database, including legality information.
    """
    print(f"Attempting to fetch '{card_name}' from local database...")
    cursor = conn.cursor()
    try:
        # Join the `cards` table with `cardLegalities` to fetch legality data
        cursor.execute("""
            SELECT c.*, cl.*
            FROM cards c
            LEFT JOIN cardLegalities cl ON c.uuid = cl.uuid
            WHERE c.name = ?
            LIMIT 1
        """, (card_name,))
        row = cursor.fetchone()

        if row is None:
            print(f"Card '{card_name}' not found in local database")
            return None

        columns = [desc[0] for desc in cursor.description]
        card = dict(zip(columns, row))
        
        # Extract legality information
        legalities = {col: card[col] for col in columns if col in [
            "alchemy", "brawl", "commander", "duel", "explorer", "future",
            "gladiator", "historic", "legacy", "modern", "oathbreaker",
            "oldschool", "pauper", "paupercommander", "penny", "pioneer",
            "predh", "premodern", "standard", "standardbrawl", "timeless",
            "vintage"
        ]}

        card["legalities"] = legalities  # Store legalities in card dictionary

        # Handle color fields which might be JSON strings or direct arrays
        colors_raw = card.get("colors")
        if isinstance(colors_raw, str):
            try:
                colors = json.loads(colors_raw) if colors_raw and colors_raw.strip() else []
            except json.JSONDecodeError:
                colors = [c.strip() for c in colors_raw.strip('[]').split(',') if c.strip()]
        else:
            colors = colors_raw if colors_raw else []

        color_identity_raw = card.get("colorIdentity")
        if isinstance(color_identity_raw, str):
            try:
                color_identity = json.loads(color_identity_raw) if color_identity_raw and color_identity_raw.strip() else []
            except json.JSONDecodeError:
                color_identity = [c.strip() for c in color_identity_raw.strip('[]').split(',') if c.strip()]
        else:
            color_identity = color_identity_raw if color_identity_raw else []

        # Clean up any quotes in the color values
        colors = [c.strip('"\'') for c in colors if c]
        color_identity = [c.strip('"\'') for c in color_identity if c]
            
        print(f"Parsed colors: {colors}")
        print(f"Parsed color identity: {color_identity}")
        print(f"Legalities: {legalities}")

        # Add legalities to the normalized dictionary
        normalized = {
            "name": card.get("name"),
            "manaCost": card.get("manaCost"),
            "oracle_text": card.get("text") or "",  # Ensure oracle_text is never None
            "type_line": card.get("type") or card.get("type_line") or "",
            "power": card.get("power"),
            "toughness": card.get("toughness"),
            "loyalty": card.get("loyalty"),
            "setCode": card.get("setCode"),
            "rarity": card.get("rarity"),
            "cmc": card.get("manaValue") or card.get("cmc") or 0,
            "colors": colors,
            "color_identity": color_identity,
            "legalities": legalities  # Ensure legalities are stored
        }

        print(f"✅ Successfully fetched '{card_name}' from local database with legality info")
        return normalized
    except sqlite3.Error as e:
        print(f"❌ Database error when fetching '{card_name}': {e}")
        return None


def fallback_fetch_card_data(card_name):
    """
    Fetches card details from the Scryfall API as a fallback.
    """
    print(f"Attempting to fetch '{card_name}' from Scryfall API...")
    url = "https://api.scryfall.com/cards/named"
    params = {"exact": card_name}
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"Error fetching '{card_name}' from Scryfall: {response.json().get('details', 'Unknown error')}")
            return None
        data = response.json()
        normalized = {
            "name": data.get("name"),
            "manaCost": data.get("mana_cost"),
            "oracle_text": data.get("oracle_text") or "",  # Ensure oracle_text is never None
            "type_line": data.get("type_line") or "",
            "power": data.get("power"),
            "toughness": data.get("toughness"),
            "loyalty": data.get("loyalty"),
            "setCode": data.get("set"),
            "rarity": data.get("rarity"),
            "cmc": data.get("cmc") or 0,
            "colors": data.get("colors") or [],
            "color_identity": data.get("color_identity") or []
        }
        print(f"Successfully fetched '{card_name}' from Scryfall")
        return normalized
    except Exception as e:
        print(f"Exception fetching '{card_name}' from Scryfall: {e}")
        return None

def fetch_card_data_with_fallback(card_name, conn):
    """
    Attempts to fetch card data from the local database.
    If not found, falls back to the Scryfall API.
    """
    if " // " in card_name:
        card_name = card_name.split(" // ")[0].strip()
        
    data = fetch_card_data(card_name, conn)
    if data is None:
        print(f"Card not found in local database, trying Scryfall API...")
        data = fallback_fetch_card_data(card_name)
        
        if data:
            print(f"✅ Fetched '{card_name}' from Scryfall API")
            
            # Default Scryfall legality handling (if missing)
            default_legalities = {
                "alchemy": None, "brawl": None, "commander": None, "duel": None,
                "explorer": None, "future": None, "gladiator": None, "historic": None,
                "legacy": None, "modern": None, "oathbreaker": None, "oldschool": None,
                "pauper": None, "paupercommander": None, "penny": None, "pioneer": None,
                "predh": None, "premodern": None, "standard": None, "standardbrawl": None,
                "timeless": None, "vintage": None
            }
            data["legalities"] = default_legalities  # Prevent missing legality key

    return data


# ----------------------
# Deck Archetype Detection (Improved)
# ----------------------

def detect_archetype(commander):
    """
    Improved archetype detection using commander abilities.
    Handles complex synergies and multiple archetypes.
    """
    if not commander:
        return "Midrange"

    oracle_text = commander.get("oracle_text", "").lower() if commander.get("oracle_text") else ""
    type_line = commander.get("type_line", "").lower()
    
    # Initialize score tracking for different archetypes
    archetype_scores = {
        "Tokens": 0,
        "Control": 0,
        "Voltron": 0,
        "Aristocrats": 0,
        "Graveyard": 0,
        "Spellslinger": 0,
        "Combo": 0,
        "Tribal": 0,
        "Ramp": 0
    }
    
    # Token strategies
    if "create" in oracle_text and "token" in oracle_text:
        archetype_scores["Tokens"] += 3
    if "populate" in oracle_text:
        archetype_scores["Tokens"] += 2
        
    # Control elements
    if any(x in oracle_text for x in ["counter target spell", "counter spell", "return target"]):
        archetype_scores["Control"] += 2
    if "draw a card" in oracle_text:
        archetype_scores["Control"] += 1
        
    # Voltron indicators
    if any(x in oracle_text for x in ["double strike", "hexproof", "indestructible", "equip"]):
        archetype_scores["Voltron"] += 2
    if "aura" in oracle_text or "equipment" in oracle_text:
        archetype_scores["Voltron"] += 2
        
    # Aristocrats and sacrifice themes
    if "sacrifice" in oracle_text:
        archetype_scores["Aristocrats"] += 3
    if "dies" in oracle_text or "when another creature dies" in oracle_text:
        archetype_scores["Aristocrats"] += 2
        
    # Graveyard strategies
    if "graveyard" in oracle_text:
        archetype_scores["Graveyard"] += 2
    if "exile" in oracle_text and "return" in oracle_text:
        archetype_scores["Graveyard"] += 1
        
    # Spellslinger detection
    if "whenever you cast" in oracle_text and "instant" in oracle_text or "sorcery" in oracle_text:
        archetype_scores["Spellslinger"] += 3
    if "copy" in oracle_text and "spell" in oracle_text:
        archetype_scores["Spellslinger"] += 2
        
    # Combo potential
    if any(x in oracle_text for x in ["untap", "extra turn", "storm", "cascade"]):
        archetype_scores["Combo"] += 2
        
    # Tribal detection
    creature_types = re.findall(r"(?:other )?([A-Za-z]+) creatures?", oracle_text)
    if creature_types:
        archetype_scores["Tribal"] += 2
        
    # Ramp strategies
    if "land" in oracle_text and any(x in oracle_text for x in ["search", "additional", "play"]):
        archetype_scores["Ramp"] += 2
    if "add {" in oracle_text:  # Mana production
        archetype_scores["Ramp"] += 2

    # Get the highest scoring archetype
    primary_archetype = max(archetype_scores.items(), key=lambda x: x[1])[0]
    
    # If nothing scored high enough, default to Midrange
    if archetype_scores[primary_archetype] < 2:
        return "Midrange"
        
    return primary_archetype

# ----------------------
# Mana Curve Module (New)
# ----------------------

def analyze_mana_curve(deck, ramp_count):
    """
    Analyzes the current mana curve of the deck.
    Returns statistics about the curve and recommendations.
    """
    curve = [0] * 8  # Track CMC 0-7+
    total_cmc = 0
    count = 0
    
    for card in deck:
        cmc = min(7, int(card.get("cmc", 0)))  # Group 7+ CMC together
        curve[cmc] += 1
        total_cmc += card.get("cmc", 0)
        count += 1
    
    avg_cmc = total_cmc / max(1, count)
    return {
        "curve": curve,
        "average_cmc": avg_cmc,
        "ramp_density": ramp_count / max(1, len(deck))
    }

def compute_mana_curve_penalty(card, desired_max_cmc, ramp_count, current_curve=None):
    """
    Returns a dynamic penalty based on the card's CMC, available ramp, and current curve.
    Reduces penalty if the deck has sufficient ramp or fits the strategy.
    """
    cmc = card.get("cmc", 0) or 0
    if cmc <= desired_max_cmc:
        return 0
        
    # Base penalty calculation
    base_penalty = (cmc - desired_max_cmc) * 10
    
    # Reduce penalty based on ramp density
    ramp_modifier = min(0.8, ramp_count * 0.1)  # Up to 80% reduction with 8+ ramp pieces
    
    # Additional curve considerations if available
    if current_curve:
        if current_curve["average_cmc"] < 3.0:  # Low curve deck
            base_penalty *= 1.2  # Increase penalty for high CMC cards
        elif current_curve["average_cmc"] > 4.0:  # High curve deck
            base_penalty *= 0.8  # Reduce penalty for high CMC cards
    
    final_penalty = base_penalty * (1 - ramp_modifier)
    return max(0, final_penalty)
# ----------------------
# Deck Theme Module
# ----------------------
def get_deck_theme(commander):
    """
    Gets deck theme from user input and commander analysis.
    """
    user_description = input("Describe your deck (e.g., Aggro, Control, Group Hug, Tokens, etc.): ")
    archetype = detect_archetype(commander) if commander else "Midrange"
    return {
        "theme": archetype,
        "keywords": user_description.lower().split()
    }
# ----------------------
# Card Selection Validation Functions 
# ----------------------
# Global list to track skipped cards
import json

# ----------------------
# Card Selection Validation Functions 
# ----------------------
# Global list to track skipped cards
skipped_cards = []

def is_valid_card_for_deck(card, commander_colors, format_type="commander"):
    """
    Checks if a card is valid for the deck based on:
    - Legality in the specified format
    - Not being a token or emblem
    - Color identity strictly matching commander
    - Proper handling of MDFCs (Modal Double-Faced Cards)
    """
    if not card:
        return False

    # Fetch and check the 'legalities' field
    legalities = card.get('legalities', None)
    
    if legalities is None:
        print(f"⚠️ No legalities data for {card.get('name', 'Unknown')} - Data might be missing!")
        skipped_cards.append({
            'name': card.get('name', 'Unknown Card'),
            'reason': f'Missing legality data for {format_type}',
        })
        return False  # Assume illegal if legality data is missing
    
    # Convert from string if necessary
    if isinstance(legalities, str):
        try:
            legalities = json.loads(legalities)
        except json.JSONDecodeError:
            print(f"❌ Failed to parse legality JSON for {card.get('name', 'Unknown')} - Marking as illegal.")
            return False

    # Format-specific legality check
    is_legal = legalities.get(format_type, 'not_legal')
    if not (is_legal and is_legal.lower() == 'legal'):  # Convert to lowercase for comparison
        return False
        
    # Check color identity if commander_colors is provided
    if commander_colors:
        card_color_identity = set(card.get('color_identity', []))
        commander_color_set = set(commander_colors)
        
        # Basic land exception
        if card.get('name') in ["Plains", "Island", "Swamp", "Mountain", "Forest"]:
            basic_map = {"Plains": ["W"], "Island": ["U"], "Swamp": ["B"], "Mountain": ["R"], "Forest": ["G"]}
            card_color = basic_map.get(card.get('name'), [])
            return any(c in commander_color_set for c in card_color)
            
        # For all other cards, check if card's color identity is a subset of commander's colors
        if not card_color_identity.issubset(commander_color_set):
            skipped_cards.append({
                'name': card.get('name', 'Unknown Card'),
                'reason': f'Color identity {card_color_identity} not compatible with commander colors {commander_colors}',
            })
            return False
    
    return True
def is_singleton_legal(card, selected_cards, allow_basic_lands=True):
    """
    Checks if adding this card would violate singleton rules.
    Handles both basic lands and MDFCs appropriately.
    """
    if not card:
        return False
        
    # Get front face name for all cards
    card_name = card.get('name', '').split(' // ')[0].lower()
    
    # Basic land handling
    basic_lands = {'plains', 'island', 'swamp', 'mountain', 'forest'}
    if allow_basic_lands and card_name in basic_lands:
        return True
    
    # Check for existing copies, accounting for MDFCs
    for existing in selected_cards:
        existing_name = existing.get('name', '').split(' // ')[0].lower()
        if existing_name == card_name:
            return False
            
    return True

def enforce_deck_size(deck, max_size):
    """
    Ensures deck meets exact size requirements while maintaining proper ratios.
    """
    if len(deck) <= max_size:
        return deck
    
    # Categorize cards while handling MDFCs correctly
    lands = []
    creatures = []
    other_spells = []
    
    for card in deck:
        type_line = card.get('type_line', '').lower().split(' // ')[0]  # Use front face type
        if 'land' in type_line:
            lands.append(card)
        elif 'creature' in type_line:
            creatures.append(card)
        else:
            other_spells.append(card)
    
    # Calculate ideal proportions
    total_cards = len(deck)
    land_ratio = len(lands) / total_cards
    creature_ratio = len(creatures) / total_cards
    
    # Calculate target numbers
    target_lands = round(max_size * land_ratio)
    target_creatures = round(max_size * creature_ratio)
    target_others = max_size - (target_lands + target_creatures)
    
    # Ensure we don't exceed max_size
    final_deck = (
        lands[:target_lands] +
        creatures[:target_creatures] +
        other_spells[:target_others]
    )
    
    # If we're still over/under, adjust other_spells
    while len(final_deck) != max_size:
        if len(final_deck) > max_size:
            if other_spells:
                other_spells.pop()
        else:
            if other_spells:
                final_deck.append(other_spells[0])
                other_spells = other_spells[1:]
    
    return final_deck

def is_singleton_legal(card, selected_cards, allow_basic_lands=True):
    """
    Checks if adding this card would violate singleton rules.
    Handles both basic lands and MDFCs appropriately.
    """
    if not card:
        return False
        
    # Get front face name for all cards
    card_name = card.get('name', '').split(' // ')[0].lower()
    
    # Basic land handling
    basic_lands = {'plains', 'island', 'swamp', 'mountain', 'forest'}
    if allow_basic_lands and card_name in basic_lands:
        return True
    
    # Check for existing copies, accounting for MDFCs
    for existing in selected_cards:
        existing_name = existing.get('name', '').split(' // ')[0].lower()
        if existing_name == card_name:
            return False
            
    return True


def enforce_deck_size(deck, max_size):
    """
    Ensures deck meets exact size requirements while maintaining proper ratios.
    """
    if len(deck) <= max_size:
        return deck
    
    # Categorize cards while handling MDFCs correctly
    lands = []
    creatures = []
    other_spells = []
    
    for card in deck:
        type_line = card.get('type_line', '').lower().split(' // ')[0]  # Use front face type
        if 'land' in type_line:
            lands.append(card)
        elif 'creature' in type_line:
            creatures.append(card)
        else:
            other_spells.append(card)
    
    # Calculate ideal proportions
    total_cards = len(deck)
    land_ratio = len(lands) / total_cards
    creature_ratio = len(creatures) / total_cards
    
    # Calculate target numbers
    target_lands = round(max_size * land_ratio)
    target_creatures = round(max_size * creature_ratio)
    target_others = max_size - (target_lands + target_creatures)
    
    # Ensure we don't exceed max_size
    final_deck = (
        lands[:target_lands] +
        creatures[:target_creatures] +
        other_spells[:target_others]
    )
    
    # If we're still over/under, adjust other_spells
    while len(final_deck) != max_size:
        if len(final_deck) > max_size:
            if other_spells:
                other_spells.pop()
        else:
            if other_spells:
                final_deck.append(other_spells[0])
                other_spells = other_spells[1:]
    
    return final_deck

# ----------------------
# Card Categorization Module
# ----------------------
def categorize_cards(cards):
    """
    Categorizes cards into:
      - Lands
      - Creatures
      - Instants
      - Sorceries
      - Artifacts
      - Planeswalkers
      - Enchantments
      - Others (if not matching above)
    """
    categories = {
        "lands": [],
        "creatures": [],
        "instants": [],
        "sorceries": [],
        "artifacts": [],
        "planeswalkers": [],
        "enchantments": [],
        "others": []
    }
    for card in cards:
        if not card:
            continue
        type_line = card.get("type_line", "").lower()
        if "land" in type_line:
            categories["lands"].append(card)
        elif "creature" in type_line:
            categories["creatures"].append(card)
        elif "instant" in type_line:
            categories["instants"].append(card)
        elif "sorcery" in type_line:
            categories["sorceries"].append(card)
        elif "artifact" in type_line:
            categories["artifacts"].append(card)
        elif "planeswalker" in type_line:
            categories["planeswalkers"].append(card)
        elif "enchantment" in type_line:
            categories["enchantments"].append(card)
        else:
            categories["others"].append(card)
    return categories

# ----------------------
# Synergy Calculation Module (Updated)
# ----------------------
def extract_keywords(card):
    """
    Extracts keywords from a card's oracle text based on a preset list.
    """
    text = card.get("oracle_text", "").lower() if card.get("oracle_text") else ""
    keywords_list = [
        "ramp", "draw", "removal", "lifelink", "trample", "haste", "counter",
        "combo", "token", "discard", "aggressive", "defensive", "control",
        "mill", "sacrifice", "reanimation", "search", "fetch"
    ]
    found = set()
    for kw in keywords_list:
        if kw in text:
            found.add(kw)
    return found

def get_keyword_weights(commander, deck_theme_info):
    """
    Sets base keyword weights and boosts those emphasized by the commander or deck theme.
    """
    base_weights = {
         "ramp": 10,
         "draw": 8,
         "removal": 7,
         "lifelink": 4,
         "trample": 4,
         "haste": 3,
         "counter": 6,
         "combo": 8,
         "token": 5,
         "discard": 4,
         "aggressive": 5,
         "defensive": 5,
         "control": 7,
         "mill": 4,
         "sacrifice": 3,
         "reanimation": 7,
         "search": 6,
         "fetch": 5
    }
    if commander:
        commander_text = commander.get("oracle_text", "").lower() if commander.get("oracle_text") else ""
        for kw in base_weights.keys():
            if kw in commander_text:
                base_weights[kw] *= 1.5
    if deck_theme_info and "keywords" in deck_theme_info:
        for kw in deck_theme_info["keywords"]:
            kw_lower = kw.lower()
            if kw_lower in base_weights:
                base_weights[kw_lower] *= 1.5
            else:
                base_weights[kw_lower] = 5
    return base_weights

def calculate_commander_synergy(card, commander):
    """
    Calculates synergy between a card and the commander based on color and keyword overlap.
    Also adds bonuses for specific commander interactions.
    """
    score = 0
    if not commander:
        return score

    commander_text = commander.get("oracle_text", "").lower() if commander.get("oracle_text") else ""
    card_text = card.get("oracle_text", "").lower() if card.get("oracle_text") else ""
    
    # Basic color/keyword synergy:
    card_colors = set(card.get("colors", []))
    commander_colors = set(commander.get("color_identity", []))
    if card_colors and commander_colors and card_colors.intersection(commander_colors):
        score += 50
    card_keywords = extract_keywords(card)
    commander_keywords = extract_keywords(commander)
    common_keywords = card_keywords.intersection(commander_keywords)
    score += len(common_keywords) * 10

    # Commander-specific interactions:
    if "copy spell" in commander_text and "copy" in card_text:
        score += 30
    if "tax" in commander_text and "opponent" in card_text:
        score += 25
    if "extra turn" in commander_text and "extra turn" in card_text:
        score += 40

    return min(score, 100)

def calculate_inherent_strength(card, keyword_weights):
    """
    Determines a card's inherent strength using its keywords and dynamic weights.
    """
    keywords = extract_keywords(card)
    return sum(keyword_weights.get(kw, 0) for kw in keywords)

def calculate_inter_deck_bonus(card, selected_cards):
    """
    Provides a bonus based on overlapping keywords with already selected cards.
    """
    bonus = 0
    card_keywords = extract_keywords(card)
    for sel in selected_cards:
        sel_keywords = extract_keywords(sel)
        bonus += len(card_keywords.intersection(sel_keywords)) * 3
    return bonus

def compute_mana_curve_penalty(card, desired_max_cmc):
    """
    Returns a penalty for a card whose converted mana cost (cmc) exceeds desired_max_cmc.
    """
    cmc = card.get("cmc", 0) or 0
    if cmc > desired_max_cmc:
        return (cmc - desired_max_cmc) * 10
    return 0

def calculate_total_synergy(card, commander, selected_cards, keyword_weights, deck_theme_info=None):
    """
    Combines commander synergy, inherent strength, and inter-deck bonus.
    Also adjusts the score based on the deck's archetype.
    """
    total = (calculate_commander_synergy(card, commander) +
             calculate_inherent_strength(card, keyword_weights) +
             calculate_inter_deck_bonus(card, selected_cards))
    
    archetype = deck_theme_info.get("theme", "Midrange").lower() if deck_theme_info else "midrange"
    card_text = card.get("oracle_text", "").lower() if card.get("oracle_text") else ""
    card_type = card.get("type_line", "").lower() if card.get("type_line") else ""
    
    if archetype == "voltron":
        if "equipment" in card_type or "aura" in card_type:
            total += 20
    elif archetype == "control":
        if "counter" in card_text or "draw" in card_text:
            total += 15
    elif archetype == "combo":
        if "infinite" in card_text or "extra turn" in card_text or "storm" in card_text:
            total += 25
    elif archetype == "tokens":
        if "create" in card_text and "token" in card_text:
            total += 30
    elif archetype == "graveyard":
        if "sacrifice" in card_text or "reanimate" in card_text:
            total += 20
    elif archetype == "ramp":
        if "add {mana}" in card_text or "land" in card_type:
            total += 15

    return total

def iterative_select_cards(candidate_cards, required_count, commander=None, keyword_weights=None, allowed_colors=None, desired_max_cmc=None, deck_theme_info=None):
    """
    Iteratively selects cards based on the highest adjusted synergy score.
    Enforces that each candidate’s color identity is a subset of allowed_colors.
    Applies mana curve penalties and archetype-specific adjustments.
    Enforces singleton rules for commander decks (or for legendary cards in non-commander decks).
    """
    if keyword_weights is None:
        keyword_weights = {}
    selected = []
    candidates = candidate_cards.copy()
    while len(selected) < required_count and candidates:
        best_card = None
        best_score = -1
        for card in candidates:
            card_colors = set(card.get("color_identity", []))
            if allowed_colors and not card_colors.issubset(allowed_colors):
                continue  # Enforce strict color identity
            card_name = card.get("name", "").lower()
            if commander is not None:
                if any(sel.get("name", "").lower() == card_name for sel in selected):
                    continue
            else:
                if "legendary" in (card.get("type_line", "").lower() if card.get("type_line") else ""):
                    if any(sel.get("name", "").lower() == card_name for sel in selected):
                        continue
            base_score = calculate_total_synergy(card, commander, selected, keyword_weights, deck_theme_info)
            penalty = compute_mana_curve_penalty(card, desired_max_cmc) if desired_max_cmc is not None else 0
            final_score = base_score - penalty
            if final_score > best_score:
                best_score = final_score
                best_card = card
        if best_card:
            selected.append(best_card)
            candidates.remove(best_card)
        else:
            break
    return selected

def get_desired_max_cmc(deck_theme_info):
    """
    Determines desired maximum CMC based on the deck theme.
    Aggro/fast decks get a lower threshold.
    """
    theme = deck_theme_info.get("theme", "").lower() if deck_theme_info else ""
    if "aggro" in theme or "fast" in theme:
        return 3
    elif "control" in theme or "ramp" in theme:
        return 5
    else:
        return 4
# ----------------------
# Color Identity Module
# ----------------------

def get_deck_colors(commander, categories):
    """
    Determines the deck's allowed colors.
    If a commander is provided, uses its color identity.
    Otherwise, aggregates colors from non-land cards.
    Returns a set of color symbols (W, U, B, R, G).
    """
    if commander:
        color_identity = commander.get("color_identity", [])
        print(f"Commander color identity: {color_identity}")
        return set(color_identity)
    
    # If no commander, look at all non-land cards
    colors = set()
    for category in ["creatures", "instants", "sorceries", "artifacts", "planeswalkers", "enchantments"]:
        for card in categories.get(category, []):
            card_colors = card.get("color_identity", [])
            colors.update(card_colors)
    
    if not colors:  # If no colors found, default to all colors
        colors = {"W", "U", "B", "R", "G"}
    
    print(f"Determined deck colors: {colors}")
    return colors
# ----------------------
# Land Utility Functions (MERGED)
# ----------------------
def is_valid_land_for_colors(land, deck_colors):
    """
    Determines if a land is valid for the deck's color identity.
    Handles special cases like fetchlands.
    """
    land_colors = set(land.get("color_identity", []))
    oracle_text = land.get("oracle_text", "").lower() if land.get("oracle_text") else ""
    
    # Always allow basic lands
    if land.get("name") in ["Plains", "Island", "Swamp", "Mountain", "Forest"]:
        return True
        
    # For mono-color decks, be more strict
    if len(deck_colors) == 1:
        # Check if land only produces mana of our color
        return land_colors.issubset(deck_colors)
    
    # For multi-color decks
    if "search your library for" in oracle_text:
        # Check if fetchland can get useful basics
        fetchable_types = []
        if "plains" in oracle_text: fetchable_types.append("W")
        if "island" in oracle_text: fetchable_types.append("U")
        if "swamp" in oracle_text: fetchable_types.append("B")
        if "mountain" in oracle_text: fetchable_types.append("R")
        if "forest" in oracle_text: fetchable_types.append("G")
        return any(color in deck_colors for color in fetchable_types)
    
    # Default case: check color identity
    return land_colors.issubset(deck_colors)

def calculate_pip_requirements(deck_colors, available_cards):
    """
    Analyzes mana pip requirements in casting costs for optimal color distribution.
    """
    color_pips = {color: 1 for color in deck_colors}
    
    for card in available_cards:
        mana_cost = card.get("manaCost", "")
        if mana_cost:
            # Handle regular mana symbols
            for color in deck_colors:
                color_pips[color] += mana_cost.count(color)
            
            # Handle hybrid mana
            hybrid_patterns = [f"{c1}/{c2}" for c1 in deck_colors for c2 in deck_colors if c1 < c2]
            for pattern in hybrid_patterns:
                if pattern in mana_cost:
                    c1, c2 = pattern.split('/')
                    color_pips[c1] += 0.5
                    color_pips[c2] += 0.5
    
    total_pips = sum(color_pips.values())
    return {color: count/total_pips for color, count in color_pips.items()}

def score_utility_land(land, deck_colors, archetype, commander=None):
    """
    Enhanced scoring for utility lands based on abilities, archetype, and commander.
    """
    score = 0
    oracle_text = land.get("oracle_text", "").lower() if land.get("oracle_text") else ""
    
    # Game-winning abilities
    combat_keywords = {
        "indestructible": 15,
        "haste": 15,
        "flying": 12,
        "unblockable": 20,
        "can't be blocked": 20,
        "double strike": 18,
        "from graveyard to": 15,
        "draw a card": 15
    }
    
    for keyword, bonus in combat_keywords.items():
        if keyword in oracle_text:
            score += bonus
    
    # Archetype-specific bonuses
    archetype_bonuses = {
        "voltron": {
            "equipment": 20,
            "equip": 20,
            "commander": 15,
            "double strike": 20
        },
        "control": {
            "draw": 20,
            "scry": 15,
            "counter": 18
        },
        "tokens": {
            "creature token": 18,
            "populate": 15
        },
        "graveyard": {
            "graveyard": 20,
            "exile from graveyard": -10  # Penalty for grave hate
        },
        "spellslinger": {
            "copy": 20,
            "instant": 15,
            "sorcery": 15
        }
    }
    
    if archetype and archetype.lower() in archetype_bonuses:
        for keyword, bonus in archetype_bonuses[archetype.lower()].items():
            if keyword in oracle_text:
                score += bonus
    
    # Commander-specific bonuses
    if commander:
        cmd_text = commander.get("oracle_text", "").lower()
        if "creature" in cmd_text and any(kw in oracle_text for kw in ["haste", "double strike", "unblockable"]):
            score += 15
        if "spell" in cmd_text and "copy" in oracle_text:
            score += 15
    
    # Penalize enters-tapped lands unless they provide significant utility
    if "enters the battlefield tapped" in oracle_text:
        if score >= 25:  # Reduce penalty for very powerful effects
            score -= 10
        elif any(bonus in oracle_text for bonus in ["scry", "gain life", "draw"]):
            score -= 15
        else:
            score -= 30
    
    # Legendary land consideration
    if "legendary" in land.get("type_line", "").lower():
        if score > 15:  # Only boost impactful legendary lands
            score += 10
    
    # Mono-color utility bonus
    if len(deck_colors) == 1:
        if any(keyword in oracle_text for keyword in ["scry", "draw", "indestructible"]):
            score += 10
    
    return score

# ----------------------
# UPDATED: Land Selection Module
# ----------------------
def select_lands(available_lands, required_count, deck_colors, commander=None, archetype=None):
    """
    Enhanced land selection with strict color identity enforcement and better utility land handling.
    """
    if not available_lands or not deck_colors:
        print("Warning: No lands available or no colors specified")
        return []
        
    print(f"Selecting lands for colors: {deck_colors}")
    
    # Filter lands by enhanced color identity validation
    def is_valid_land(land):
        if not land:
            return False
            
        name = land.get('name', '')
        oracle_text = land.get('oracle_text', '').lower() if land.get('oracle_text') else ''
        
        # Basic land handling - make this more strict
        if name in ["Plains", "Island", "Swamp", "Mountain", "Forest"]:
            basic_map = {
                "Plains": "W" in deck_colors,
                "Island": "U" in deck_colors,
                "Swamp": "B" in deck_colors,
                "Mountain": "R" in deck_colors,
                "Forest": "G" in deck_colors
            }
            return basic_map[name]
        
        # Mono-color specific handling
        if len(deck_colors) == 1:
            color = list(deck_colors)[0]
            produces_color = f"add {{{color}}}" in oracle_text
            
            # Define high-value utility effects
            utility_effects = [
                'draw a card',
                'scry',
                'search your library',
                'exile',
                'destroy target'
            ]
            
            has_utility = any(effect in oracle_text for effect in utility_effects)
            
            # Strict color identity check for mono-color
            land_colors = set(land.get('color_identity', []))
            color_valid = land_colors.issubset(set(deck_colors))
            
            return (produces_color or has_utility) and color_valid
        
        # Multi-color handling with strict color identity check
        land_colors = set(land.get('color_identity', []))
        if not land_colors.issubset(set(deck_colors)):
            print(f"DEBUG: Skipping land {name} - colors {land_colors} not subset of {deck_colors}")
            return False
            
        return True
    
    valid_lands = [land for land in available_lands if is_valid_land(land)]
    
    # Track selected lands for singleton enforcement
    selected = []
    used_names = set()
    
    # Separate basics and non-basics
    basic_lands = []
    nonbasic_lands = []
    
    for land in valid_lands:
        name = land.get('name', '')
        if name in ["Plains", "Island", "Swamp", "Mountain", "Forest"]:
            if name not in used_names:  # Only add one copy of each basic initially
                basic_lands.append(land)
                used_names.add(name)
        else:
            nonbasic_lands.append(land)
    
    # Score and sort non-basic lands
    scored_nonbasics = [(land, score_utility_land(land, deck_colors, archetype, commander))
                        for land in nonbasic_lands]
    scored_nonbasics.sort(key=lambda x: x[1], reverse=True)
    
    # Add high-scoring utility lands first
    for land, score in scored_nonbasics:
        if len(selected) >= required_count:
            break
            
        land_name = land.get('name', '').lower()
        if score > 0 and land_name not in used_names:
            selected.append(land)
            used_names.add(land_name)
    
    # Fill remaining slots with basic lands
    remaining = required_count - len(selected)
    if remaining > 0 and basic_lands:
        while len(selected) < required_count:
            selected.append(basic_lands[0])  # Add copies of the appropriate basic land
    
    return selected
# ----------------------
# NEW: Equipment and Aura Enhancement Module
# ----------------------
def score_equipment_aura(card, archetype, commander=None):
    """
    Scores equipment and auras based on their combat relevance and synergies.
    """
    score = 0
    card_text = card.get("oracle_text", "").lower() if card.get("oracle_text") else ""
    card_type = card.get("type_line", "").lower() if card.get("type_line") else ""
    
    # Combat keywords and their values
    keywords = {
        "double strike": 25,
        "lifelink": 20,
        "flying": 15,
        "first strike": 15,
        "vigilance": 15,
        "trample": 15,
        "hexproof": 25,
        "indestructible": 25,
        "protection": 20,
        "haste": 15
    }
    
    # Score based on keywords granted
    keyword_count = 0
    for keyword, value in keywords.items():
        if keyword in card_text:
            score += value
            keyword_count += 1
    
    # Bonus for equipment/auras that grant multiple keywords
    if keyword_count >= 2:
        score += 15
    
    # Archetype-specific bonuses
    if archetype == "voltron":
        score *= 1.5  # 50% bonus for voltron decks
    elif commander and "odric" in commander.get("name", "").lower():
        score *= 1.3  # 30% bonus for Odric keyword tribal
        
    # Power/toughness bonuses
    if "+2/" in card_text or "/+2" in card_text:
        score += 10
    elif "+3/" in card_text or "/+3" in card_text:
        score += 15
    elif "+4/" in card_text or "/+4" in card_text:
        score += 20
        
    # Penalize high equip costs
    equip_cost_match = re.search(r"equip {(\d+)}", card_text)
    if equip_cost_match:
        equip_cost = int(equip_cost_match.group(1))
        if equip_cost >= 4:
            score -= 15
        elif equip_cost >= 3:
            score -= 10
            
    return score

# ----------------------
# Spellslinger Analysis Module (NEW)
# ----------------------

def is_spellslinger_commander(commander):
    """
    Determines if a commander is spell-focused.
    """
    if not commander:
        return False
        
    oracle_text = commander.get("oracle_text", "").lower()
    spellslinger_indicators = [
        "whenever you cast",
        "instant or sorcery",
        "noncreature spell",
        "copy target spell",
        "prowess",
        "magecraft"
    ]
    
    return any(indicator in oracle_text for indicator in spellslinger_indicators)

def get_spell_synergy(card, is_spellslinger):
    """
    Calculates how well a card fits in a spellslinger strategy.
    """
    if not is_spellslinger:
        return 0
        
    score = 0
    card_text = card.get("oracle_text", "").lower()
    card_type = card.get("type_line", "").lower()
    
    # High synergy for instants and sorceries
    if "instant" in card_type or "sorcery" in card_type:
        score += 30
        
    # Synergy for spell-related effects
    spell_synergies = [
        ("prowess", 15),
        ("magecraft", 20),
        ("copy target spell", 25),
        ("whenever you cast", 20),
        ("instant or sorcery", 15),
        ("flashback", 15),
        ("retrace", 15),
        ("jump-start", 15)
    ]
    
    for keyword, bonus in spell_synergies:
        if keyword in card_text:
            score += bonus
            
    return score

# ----------------------
# Enhanced Strategy Detection Module
# ----------------------
def analyze_deck_strategy(commander=None, deck_theme_info=None):
    """
    Comprehensive strategy analysis that detects multiple deck archetypes
    and their specific requirements.
    """
    strategy = {
        "primary_archetype": "midrange",
        "sub_archetypes": [],
        "lands_required": 36,
        "creatures_required": 25,
        "spells_required": 38,
        "specific_requirements": {
            "min_instants_sorceries": 0,
            "min_artifacts": 0,
            "min_enchantments": 0,
            "min_planeswalkers": 0,
            "creature_keywords_matter": False,
            "tribal_type": None,
            "spell_matters": False,
            "graveyard_matters": False
        }
    }
    
    if not commander:
        return strategy
        
    oracle_text = commander.get("oracle_text", "").lower() if commander.get("oracle_text") else ""
    name = commander.get("name", "").lower()
    
    # Core strategy detection
    if is_spellslinger_commander(commander):
        strategy["primary_archetype"] = "spellslinger"
        strategy["specific_requirements"]["spell_matters"] = True
        strategy["specific_requirements"]["min_instants_sorceries"] = 30
        strategy["lands_required"] = 36
        strategy["creatures_required"] = 15
        strategy["spells_required"] = 48
    
    # Creature-focused strategy detection
    creature_keywords = ["flying", "first strike", "double strike", "deathtouch", "lifelink", 
                        "trample", "vigilance", "haste", "protection", "hexproof"]
    keyword_count = sum(1 for kw in creature_keywords if kw in oracle_text)
    
    if keyword_count >= 2 or "creatures you control" in oracle_text:
        strategy["sub_archetypes"].append("creature_keywords")
        strategy["specific_requirements"]["creature_keywords_matter"] = True
        if "odric" in name:
            strategy["creatures_required"] = 35
            strategy["spells_required"] = 28
    
    # Tribal detection
    tribal_types = {
        "dragon": ("dragon", 33),
        "zombie": ("zombie", 35),
        "elf": ("elf", 33),
        "goblin": ("goblin", 35),
        "dinosaur": ("dinosaur", 32),
        "vampire": ("vampire", 33),
        "wizard": ("wizard", 30),
        "warrior": ("warrior", 33)
    }
    
    for tribe, (type_name, creature_count) in tribal_types.items():
        if tribe in oracle_text or f"{tribe}s" in oracle_text:
            strategy["sub_archetypes"].append("tribal")
            strategy["specific_requirements"]["tribal_type"] = type_name
            strategy["creatures_required"] = creature_count
            strategy["spells_required"] = 99 - strategy["lands_required"] - creature_count
            break
    
    # Archetype-specific adjustments from theme info
    if deck_theme_info:
        theme = deck_theme_info.get("theme", "").lower()
        if theme == "control":
            strategy["lands_required"] = 38
            strategy["specific_requirements"]["min_instants_sorceries"] = 20
            strategy["sub_archetypes"].append("control")
        elif theme == "voltron":
            strategy["lands_required"] = 34
            strategy["specific_requirements"]["min_artifacts"] = 15
            strategy["sub_archetypes"].append("voltron")
        elif theme == "tokens":
            strategy["specific_requirements"]["min_enchantments"] = 10
            strategy["sub_archetypes"].append("tokens")
        elif theme == "graveyard":
            strategy["specific_requirements"]["graveyard_matters"] = True
            strategy["sub_archetypes"].append("graveyard")
    
    return strategy

# ----------------------
# Enhanced Card Selection Module
# ----------------------
def score_card_for_strategy(card, strategy, commander=None, selected_cards=None):
    """
    Enhanced scoring system that considers multiple strategies and requirements.
    """
    if not card:
        return 0
        
    score = 0
    card_text = card.get("oracle_text", "").lower() if card.get("oracle_text") else ""
    card_type = card.get("type_line", "").lower() if card.get("type_line") else ""
    
    # Base scoring from existing synergy calculation
    if commander:
        score += calculate_commander_synergy(card, commander)
    
    # Strategy-specific scoring
    if strategy["specific_requirements"]["spell_matters"]:
        if "instant" in card_type or "sorcery" in card_type:
            score += 20
        if "copy" in card_text and "spell" in card_text:
            score += 15
            
    if strategy["specific_requirements"]["creature_keywords_matter"]:
        keywords = ["flying", "first strike", "double strike", "deathtouch", "lifelink",
                   "trample", "vigilance", "haste", "protection", "hexproof"]
        keyword_count = sum(1 for kw in keywords if kw in card_text)
        score += keyword_count * 15
        
    if strategy["specific_requirements"]["tribal_type"]:
        tribal_type = strategy["specific_requirements"]["tribal_type"]
        if tribal_type in card_type or f"{tribal_type}s" in card_type:
            score += 25
            
    if "graveyard" in strategy["sub_archetypes"]:
        if "graveyard" in card_text or "return" in card_text and "from your graveyard" in card_text:
            score += 20
            
    # Equipment/Aura scoring for Voltron
    if "voltron" in strategy["sub_archetypes"]:
        if "equipment" in card_type or "aura" in card_type:
            score += score_equipment_aura(card, "voltron", commander)
            
    # Control elements
    if "control" in strategy["sub_archetypes"]:
        control_keywords = ["counter target", "destroy target", "exile target"]
        if any(kw in card_text for kw in control_keywords):
            score += 15
            
    return score
# ----------------------
# Deck Requirements Module
# ----------------------
def check_and_adjust_requirements(deck, available_cards, deck_colors, commander=None):
    """
    Checks and adjusts deck for minimum ramp and card draw requirements.
    """
    if not deck or not available_cards:
        return deck
        
    # Define minimum requirements for mono-white
    requirements = {
        'ramp': {
            'min_count': 8,
            'patterns': [
                'search your library for a.*plains',
                'search your library for a basic.*plains',
                'search.*for a basic land',
                'land.*onto the battlefield',
                'add {W}',
                'add one mana of any color',
                'you may put a.*land.*onto the battlefield'
            ]
        },
        'draw': {
            'min_count': 6,
            'patterns': [
                'draw a card',
                'draw cards',
                'investigate',
                'whenever.*you may draw',
                'draw.*for each',
                'look at the top.*you may reveal'
            ]
        }
    }
    
    for category, req in requirements.items():
        # Count current cards meeting requirement
        current_count = sum(
            1 for card in deck
            if card.get('oracle_text') and  # Check if oracle_text exists
            any(pattern in card.get('oracle_text', '').lower() 
                for pattern in req['patterns'])
        )
        
        if current_count < req['min_count']:
            needed = req['min_count'] - current_count
            
            # Find valid candidates from available cards
            candidates = []
            for card in available_cards:
                # Skip if card has no oracle text
                if not card.get('oracle_text'):
                    continue
                    
                # Check if card meets pattern requirement
                meets_pattern = any(pattern in card.get('oracle_text', '').lower() 
                                  for pattern in req['patterns'])
                
                # Check if card is valid for deck and follows singleton rule
                if (meets_pattern and 
                    is_valid_card_for_deck(card, deck_colors) and 
                    is_singleton_legal(card, deck)):
                    candidates.append(card)
            
            # Sort candidates by synergy if we have a commander
            if commander and candidates:
                candidates.sort(
                    key=lambda x: calculate_total_synergy(
                        x, commander, deck, 
                        get_keyword_weights(commander, None),
                        None
                    ),
                    reverse=True
                )
            
            # Add best candidates while maintaining deck size
            for card in candidates[:needed]:
                if len(deck) < 99:  # Commander deck size limit
                    deck.append(card)
                    print(f"Added {card.get('name')} for {category} requirement")
    
    return deck
##############
## Build Deck Function ##
##############
def build_deck(categories, commander=None, partner_commander=None, deck_size=None,
               lands_required=None, creatures_required=None, spells_required=None,
               keyword_weights=None, deck_theme_info=None):
    """
    Enhanced deck construction that enforces proper card counts and singleton rules.
    """
    # Get comprehensive strategy analysis
    strategy = analyze_deck_strategy(commander, deck_theme_info)
    
    # Get commander colors
    commander_colors = set()
    if commander:
        commander_colors.update(commander.get('color_identity', []))
    if partner_commander:
        commander_colors.update(partner_commander.get('color_identity', []))
    commander_colors = list(commander_colors)
    
    print(f"DEBUG: Commander colors detected: {commander_colors}")
    
    # Initialize deck size and requirements
    if commander:
        max_size = 99  # 99 cards + 1 commander = 100 total
        if lands_required is None:
            lands_required = strategy["lands_required"]
        if creatures_required is None:
            creatures_required = strategy["creatures_required"]
        if spells_required is None:
            spells_required = max_size - (lands_required + creatures_required)
    else:
        max_size = deck_size or DEFAULT_DECK_SIZE
        if lands_required is None:
            lands_required = 24
        if creatures_required is None:
            creatures_required = 20
        if spells_required is None:
            spells_required = max_size - (lands_required + creatures_required)
    
    print(f"\nBuilding {max_size}-card deck with commander colors: {commander_colors}")
    
    deck = []
    used_cards = set()  # Track all cards added to the deck

    # Pre-filter all categories to remove invalid cards
    for category in categories:
        categories[category] = [
            card for card in categories[category]
            if is_valid_card_for_deck(card, commander_colors)
        ]
    
    # Land selection with proper basic land handling
    available_lands = categories.get("lands", [])
    if available_lands:
        # Get basic lands for commander's colors
        basic_lands = []
        color_to_basic = {
            'W': 'Plains', 'U': 'Island', 'B': 'Swamp',
            'R': 'Mountain', 'G': 'Forest'
        }
        for color in commander_colors:
            matching_basics = [land for land in available_lands 
                             if land.get('name') == color_to_basic.get(color)]
            if matching_basics:
                basic_lands.append(matching_basics[0])
        
        # Select non-basic lands first
        selected_lands = select_lands(available_lands, lands_required, commander_colors,
                                    commander, strategy["primary_archetype"])
        
        # Fill remaining slots with appropriate basic lands
        while len(selected_lands) < lands_required and basic_lands:
            selected_lands.append(basic_lands[0])
        
        deck.extend(selected_lands[:lands_required])
    
    # Creature selection
    available_creatures = categories.get("creatures", [])
    if available_creatures:
        valid_creatures = [
            creature for creature in available_creatures 
            if is_singleton_legal(creature, deck) and 
               is_valid_card_for_deck(creature, commander_colors)
        ]
        
        scored_creatures = [(creature, score_card_for_strategy(creature, strategy, commander, deck))
                          for creature in valid_creatures]
        scored_creatures.sort(key=lambda x: x[1], reverse=True)
        
        selected_creatures = []
        for creature, _ in scored_creatures:
            if len(selected_creatures) >= creatures_required:
                break
            creature_name = creature.get('name', '').lower()
            if (is_valid_card_for_deck(creature, commander_colors) and 
                creature_name not in used_cards):
                selected_creatures.append(creature)
                used_cards.add(creature_name)
        
        deck.extend(selected_creatures)
    
    # Spell selection
    remaining_slots = max_size - len(deck)
    available_spells = []
    for category in ["instants", "sorceries", "artifacts", "enchantments", "planeswalkers"]:
        category_spells = categories.get(category, [])
        available_spells.extend([
            spell for spell in category_spells
            if is_valid_card_for_deck(spell, commander_colors)
        ])
    
    if available_spells:
        valid_spells = [
            spell for spell in available_spells
            if is_singleton_legal(spell, deck)
        ]
        
        scored_spells = [(spell, score_card_for_strategy(spell, strategy, commander, deck))
                        for spell in valid_spells]
        scored_spells.sort(key=lambda x: x[1], reverse=True)
        
        selected_spells = []
        for spell, _ in scored_spells:
            if len(selected_spells) >= remaining_slots:
                break
            spell_name = spell.get('name', '').lower()
            if spell_name not in used_cards:
                selected_spells.append(spell)
                used_cards.add(spell_name)
        
        deck.extend(selected_spells)
     # Combine all available cards from categories for requirements check
    available_cards = []
    for category_list in categories.values():
        available_cards.extend(category_list)
    
    # Check and adjust for minimum requirements
    deck = check_and_adjust_requirements(deck, available_cards, commander_colors, commander)
    # Final size check and adjustment
    while len(deck) < max_size:
        # First try to find commander-color-appropriate basic lands
        basic_lands = []
        if commander_colors:
            for land in available_lands:
                name = land.get("name")
                if name == "Plains" and "W" in commander_colors:
                    basic_lands.append(land)
                elif name == "Island" and "U" in commander_colors:
                    basic_lands.append(land)
                elif name == "Swamp" and "B" in commander_colors:
                    basic_lands.append(land)
                elif name == "Mountain" and "R" in commander_colors:
                    basic_lands.append(land)
                elif name == "Forest" and "G" in commander_colors:
                    basic_lands.append(land)
        
        # If no color-appropriate basics found, try any available basic
        if not basic_lands:
            basic_lands = [land for land in available_lands 
                         if land.get("name") in ["Plains", "Island", "Swamp", "Mountain", "Forest"]]
        
        if basic_lands:
            # Prefer basic lands that match commander colors
            matching_basics = [land for land in basic_lands 
                             if is_valid_card_for_deck(land, commander_colors)]
            if matching_basics:
                deck.append(matching_basics[0])
            else:
                deck.append(basic_lands[0])
            print(f"Added basic land: {deck[-1].get('name')} (Current deck size: {len(deck)})")
        else:
            print("Warning: No basic lands available to complete the deck")
            break
    
    # Final verification
    print(f"\nFinal deck composition:")
    print(f"Total cards: {len(deck)}")
    print(f"Colors: {commander_colors}")
    print(f"Lands: {sum(1 for card in deck if 'Land' in card.get('type_line', ''))}")
    print(f"Creatures: {sum(1 for card in deck if 'Creature' in card.get('type_line', ''))}")
    print(f"Other spells: {sum(1 for card in deck if 'Land' not in card.get('type_line', '') and 'Creature' not in card.get('type_line', ''))}")
    
    if len(deck) != max_size:
        print(f"Warning: Deck contains {len(deck)} cards instead of {max_size}")
    
    return deck
# ----------------------
# LLM Deck Explanation Module
# ----------------------
def get_deck_explanation(deck, commander=None):
    """
    Uses the OpenAI API to generate a concise deck explanation.
    """
    deck_summary = ""
    if commander:
        deck_summary += f"Commander: {commander.get('name', 'Unknown')}\n"
    deck_summary += "Deck List:\n"
    for card in deck:
        deck_summary += f"- {card.get('name', 'Unknown')} ({card.get('type_line', 'No type info')})\n"
    prompt = (
        "You are an expert Magic: The Gathering deck strategist. "
        "Based on the following deck list, provide a concise explanation of the deck's win strategy, its strengths, and key synergies between cards. "
        "Describe what the deck aims to do and how it leverages its components to achieve victory.\n\n"
        f"{deck_summary}"
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert Magic: The Gathering deck strategist."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        explanation = response["choices"][0]["message"]["content"]
        return explanation
    except Exception as e:
        return f"Error generating explanation: {e}"

# ----------------------
# Output Module
# ----------------------
def print_deck(deck, commander=None):
    """
    Prints the recommended deck in the simple "1x [card name]" format.
    Displays the commander separately (if any).
    """
    print("\nRecommended Deck:")
    if commander:
        print(f"Commander: 1x {commander.get('name', 'Unknown')}")
    
    for card in deck:
        print(f"1x {card.get('name', 'Unknown')}")

# ----------------------
# Main Program Flow
# ----------------------
def main():
    print("Welcome to the MTG Deck Builder!")
    print("Build optimized decks for both Standard and Commander/EDH formats.")
    
    # Check if database exists
    if not os.path.exists(DB_FILENAME):
        print(f"Error: Database file '{DB_FILENAME}' not found in current directory.")
        return
        
    file_path = input("Enter the path to your card list file (e.g., card_list.txt): ").strip()
    card_names = read_card_list(file_path)
    if not card_names:
        print("No cards found. Exiting.")
        return
        
    print(f"Successfully read {len(card_names)} cards from {file_path}")

    # Open and validate the SQLite database connection
    try:
        conn = sqlite3.connect(DB_FILENAME)
        # Test the connection
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cards'")
        if not cursor.fetchone():
            print("Error: Database file exists but does not contain the 'cards' table.")
            return
        print("Successfully connected to the database.")
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return

    commander = None
    partner_commander = None
    use_commander = input("Do you want to specify a Commander card? (y/n): ").strip().lower()
    
    if use_commander == 'y':
        commander_name = input("Enter the name of your Commander: ").strip()
        print(f"Searching for commander: {commander_name}")
        
        commander = fetch_card_data_with_fallback(commander_name, conn)
        if commander:
            print(f"Found commander: {commander.get('name')} with oracle text: {commander.get('oracle_text', 'No oracle text')}")
            
            # Check for Partner ability
            if 'partner' in commander.get('oracle_text', '').lower():
                use_partner = input("This commander has Partner. Would you like to add a partner commander? (y/n): ").strip().lower()
                if use_partner == 'y':
                    partner_name = input("Enter the name of the partner commander: ").strip()
                    partner_commander = fetch_card_data_with_fallback(partner_name, conn)
                    
                    if partner_commander:
                        # Validate partner compatibility
                        is_compatible, reason = check_partner_compatibility(commander, partner_commander)
                        if not is_compatible:
                            print(f"Invalid partner: {reason}")
                            partner_commander = None
                        else:
                            print(f"Valid partner commander: {partner_commander.get('name')}")
                            print(f"Partner commander oracle text: {partner_commander.get('oracle_text', 'No oracle text')}")
                            
                            # Get the primary strategic commander
                            primary_cmdr, secondary_cmdr, strategy_note = get_partner_strategy_emphasis(commander, partner_commander)
                            print(f"\nStrategy Note: {strategy_note}")
                            
                            # Update commander to primary for strategy purposes
                            commander = primary_cmdr
                            partner_commander = secondary_cmdr
                    else:
                        print(f"Error: Partner commander '{partner_name}' not found.")
        else:
            print(f"Error: Commander '{commander_name}' not found in database or via Scryfall.")
            return  # Exit if commander not found
            
    deck_theme_info = get_deck_theme(commander)  # Auto-detect archetype if commander is provided

    if commander:
        deck_size = 98 if partner_commander else 99  # Adjust for partner commander
        # Land count will be dynamically set in build_deck based on archetype
        creatures_required = 25
        spells_required = deck_size  # Placeholder; build_deck will adjust lands
    else:
        deck_size = DEFAULT_DECK_SIZE
        custom = input("Do you want to customize deck composition? (y/n): ").strip().lower()
        if custom == "y":
            try:
                lands_required = int(input("Enter number of lands (default 24): ") or 24)
                creatures_required = int(input("Enter number of creatures (default 20): ") or 20)
            except ValueError:
                print("Invalid input. Using default composition.")
                lands_required, creatures_required = 24, 20
        else:
            lands_required, creatures_required = 24, 20
        spells_required = deck_size - (lands_required + creatures_required)
    
    print("Fetching card details from local SQLite database (with fallback to Scryfall)...")
    fetched_cards = []
    unique_card_names = set(card_names)
    card_data_map = {}
    for name in unique_card_names:
        data = fetch_card_data_with_fallback(name, conn)
        if data:
            card_data_map[name] = data
    for name in card_names:
        if name in card_data_map:
            fetched_cards.append(card_data_map[name])
    
    if not fetched_cards:
        print("No valid cards fetched. Exiting.")
        conn.close()
        return

    categories = categorize_cards(fetched_cards)
    
    # If we have partners, combine their color identities and analyze their synergy
    if partner_commander:
        partner_synergy = analyze_partner_synergy(commander, partner_commander)
        print("\nPartner Synergy Analysis:")
        print(f"Synergy Score: {partner_synergy['score']}/100")
        for note in partner_synergy['notes']:
            print(f"- {note}")
    
    keyword_weights = get_keyword_weights(commander, deck_theme_info)
    
    # Updated build_deck call with correct parameters
    deck = build_deck(
        categories=categories,
        commander=commander,
        partner_commander=partner_commander,
        deck_size=deck_size,
        lands_required=lands_required if 'lands_required' in locals() else None,
        creatures_required=creatures_required,
        spells_required=spells_required,
        keyword_weights=keyword_weights,
        deck_theme_info=deck_theme_info
    )
    
    # Print deck information
    print_deck(deck, commander)
    print("\nGenerating deck explanation...")
    explanation = get_deck_explanation(deck, commander)
    print("\nDeck Explanation:")
    print(explanation)
    
    conn.close()

if __name__ == "__main__":
    main()