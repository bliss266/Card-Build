from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
from mtg_deck_builder_v1 import (fetch_card_data_with_fallback, check_partner_compatibility,
                                 build_deck, categorize_cards, get_deck_theme, is_valid_card_for_deck)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

DB_FILENAME = "AllPrintings.sqlite"

# Global list to track skipped cards for debugging
skipped_cards = []

@app.route('/api/validate-commander', methods=['POST'])
def validate_commander():
    data = request.json
    commander_name = data.get('name')
    
    try:
        conn = sqlite3.connect(DB_FILENAME)
        commander = fetch_card_data_with_fallback(commander_name, conn)
        conn.close()
        
        if not commander:
            return jsonify({'error': 'Commander not found'}), 404
            
        # Check if card can be a commander
        type_line = commander.get('type_line', '').lower()
        if 'legendary' not in type_line or 'creature' not in type_line:
            return jsonify({'error': 'Card must be a legendary creature'}), 400
            
        return jsonify({
            'name': commander.get('name'),
            'oracle_text': commander.get('oracle_text'),
            'color_identity': commander.get('color_identity'),
            'has_partner': 'partner' in commander.get('oracle_text', '').lower()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-partner', methods=['POST'])
def check_partner():
    data = request.json
    commander1_name = data.get('commander1')
    commander2_name = data.get('commander2')
    
    try:
        conn = sqlite3.connect(DB_FILENAME)
        commander1 = fetch_card_data_with_fallback(commander1_name, conn)
        commander2 = fetch_card_data_with_fallback(commander2_name, conn)
        conn.close()
        
        if not commander1 or not commander2:
            return jsonify({'error': 'One or both commanders not found'}), 404
            
        is_compatible, reason = check_partner_compatibility(commander1, commander2)
        return jsonify({
            'is_compatible': is_compatible,
            'reason': reason
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/build-deck', methods=['POST'])
def build_deck_api():
    data = request.json
    card_list = data.get('cardList', '').split('\n')
    format_type = data.get('format', 'commander')  # Default to commander format
    commander_name = data.get('commander')
    partner_name = data.get('partnerCommander')
    deck_goal = data.get('deckGoal')

    try:
        conn = sqlite3.connect(DB_FILENAME)

        # Fetch commanders if provided
        commander = None
        partner = None
        if commander_name:
            commander = fetch_card_data_with_fallback(commander_name, conn)
        if partner_name:
            partner = fetch_card_data_with_fallback(partner_name, conn)
        
        # Ensure commanders are valid
        if commander and ('legendary' not in commander.get('type_line', '').lower() or 'creature' not in commander.get('type_line', '').lower()):
            return jsonify({'error': f"{commander_name} is not a valid commander"}), 400
        if partner and ('legendary' not in partner.get('type_line', '').lower() or 'creature' not in partner.get('type_line', '').lower()):
            return jsonify({'error': f"{partner_name} is not a valid commander"}), 400

        # Fetch all cards from the list and filter by legality
        fetched_cards = []
        for card_line in card_list:
            if card_line.strip():
                card_name = card_line.split('x')[-1].strip()
                card = fetch_card_data_with_fallback(card_name, conn)
                if card and is_valid_card_for_deck(card, commander.get('color_identity', []) if commander else [], format_type):
                    fetched_cards.append(card)

        conn.close()

        # Categorize cards
        categories = categorize_cards(fetched_cards)

        # Get deck theme
        deck_theme_info = {'theme': 'unknown', 'keywords': deck_goal.lower().split()} if deck_goal else None

        # Build the deck
        deck = build_deck(
            categories=categories,
            commander=commander,
            partner_commander=partner,
            deck_theme_info=deck_theme_info
        )

        # Format response
        response = {
            'commander': commander.get('name') if commander else None,
            'partner': partner.get('name') if partner else None,
            'deck_size': len(deck),
            'cards': [{
                'name': card.get('name'),
                'type': card.get('type_line'),
                'cmc': card.get('cmc')
            } for card in deck],
            'skipped_cards': skipped_cards[:5]  # Limit to 5 to avoid too much output
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
