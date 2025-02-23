import sqlite3
import mtg_deck_builder_v1

# Connect to SQLite
conn = sqlite3.connect("C:/Users/pando/OneDrive/Desktop/MTG Deck Builder/Backend/allprintings.sqlite")

# Fetch card data
card = mtg_deck_builder_v1.fetch_card_data_with_fallback("Emeria, the Sky Ruin", conn)

# Verify legality check
is_legal = mtg_deck_builder_v1.is_valid_card_for_deck(card, ["W"], "commander")

# Print the result
print("Final Test - Card Legal?", is_legal)  # Should print True if fixed

# Close the connection
conn.close()
