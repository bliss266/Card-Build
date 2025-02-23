import React, { useState, useEffect } from 'react';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';

const API_BASE_URL = 'http://localhost:5000/api';

const DeckBuilder = () => {
  const [state, setState] = useState({
    step: 1,
    format: '',
    cardList: '',
    useCommander: false,
    commanderName: '',
    partnerCommander: '',
    deckGoal: '',
    loading: false,
    error: null,
    result: null,
    hasPartnerAbility: false
  });

  const handleFormatChange = (format) => {
    setState(prev => ({
      ...prev,
      format,
      step: 2,
      // Reset commander-related state when format changes
      commanderName: '',
      partnerCommander: '',
      useCommander: format === 'commander'
    }));
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (file) {
      try {
        const text = await file.text();
        setState(prev => ({
          ...prev,
          cardList: text,
          error: null
        }));
      } catch (error) {
        setState(prev => ({
          ...prev,
          error: 'Error reading file. Please try again.'
        }));
      }
    }
  };

  const handleCommanderInput = async (e, isPartner = false) => {
    const name = e.target.value;
    
    setState(prev => ({
      ...prev,
      loading: true,
      error: null,
      [isPartner ? 'partnerCommander' : 'commanderName']: name
    }));

    if (!name) {
      setState(prev => ({
        ...prev,
        loading: false,
        hasPartnerAbility: false
      }));
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/validate-commander`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, isPartner })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Invalid commander name');
      }

      const data = await response.json();
      
      // If this is the main commander, check if it has partner ability
      if (!isPartner) {
        setState(prev => ({
          ...prev,
          hasPartnerAbility: data.has_partner,
          loading: false,
          error: null
        }));
      } else {
        // If this is a partner, validate compatibility
        const partnerResponse = await fetch(`${API_BASE_URL}/check-partner`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            commander1: state.commanderName,
            commander2: name
          })
        });

        const partnerData = await partnerResponse.json();
        if (!partnerData.is_compatible) {
          throw new Error(partnerData.reason);
        }

        setState(prev => ({
          ...prev,
          loading: false,
          error: null
        }));
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        loading: false,
        error: `Error validating commander: ${error.message}`,
        [isPartner ? 'partnerCommander' : 'commanderName']: ''
      }));
    }
  };

  const handleBuildDeck = async () => {
    if (!state.cardList) {
      setState(prev => ({
        ...prev,
        error: 'Please provide a card list'
      }));
      return;
    }

    setState(prev => ({
      ...prev,
      loading: true,
      error: null
    }));

    try {
      const response = await fetch(`${API_BASE_URL}/build-deck`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          format: state.format,
          cardList: state.cardList,
          commander: state.commanderName,
          partnerCommander: state.partnerCommander,
          deckGoal: state.deckGoal
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Error building deck');
      }

      const result = await response.json();
      setState(prev => ({
        ...prev,
        loading: false,
        result,
        step: 4 // Move to results display
      }));
    } catch (error) {
      setState(prev => ({
        ...prev,
        loading: false,
        error: `Error building deck: ${error.message}`
      }));
    }
  };

  const renderDeckList = () => {
    if (!state.result) return null;

    const categorizedCards = {
      Commander: [state.result.commander],
      Partner: state.result.partner ? [state.result.partner] : [],
      Creatures: [],
      Instants: [],
      Sorceries: [],
      Artifacts: [],
      Enchantments: [],
      Planeswalkers: [],
      Lands: []
    };

    state.result.cards.forEach(card => {
      const type = card.type.toLowerCase();
      if (type.includes('creature')) categorizedCards.Creatures.push(card);
      else if (type.includes('instant')) categorizedCards.Instants.push(card);
      else if (type.includes('sorcery')) categorizedCards.Sorceries.push(card);
      else if (type.includes('artifact')) categorizedCards.Artifacts.push(card);
      else if (type.includes('enchantment')) categorizedCards.Enchantments.push(card);
      else if (type.includes('planeswalker')) categorizedCards.Planeswalkers.push(card);
      else if (type.includes('land')) categorizedCards.Lands.push(card);
    });

    return (
      <div className="space-y-4">
        {Object.entries(categorizedCards).map(([category, cards]) => 
          cards.length > 0 && (
            <div key={category}>
              <h3 className="font-bold text-lg mb-2">{category} ({cards.length})</h3>
              <ul className="list-disc pl-5">
                {cards.map((card, index) => (
                  <li key={index} className="text-sm">
                    {card.name} {card.cmc ? `(${card.cmc} CMC)` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )
        )}
      </div>
    );
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      {state.error && (
        <Alert variant="destructive" className="mb-6">
          <AlertTitle>Error</AlertTitle>
          {state.error}
        </Alert>
      )}

      {/* Step 1: Format Selection */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>What kind of deck are you building?</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <label className="flex items-center space-x-2">
              <input
                type="radio"
                name="format"
                value="standard"
                checked={state.format === 'standard'}
                onChange={() => handleFormatChange('standard')}
                className="h-4 w-4"
              />
              <span>Standard</span>
            </label>
            <label className="flex items-center space-x-2">
              <input
                type="radio"
                name="format"
                value="commander"
                checked={state.format === 'commander'}
                onChange={() => handleFormatChange('commander')}
                className="h-4 w-4"
              />
              <span>Commander/EDH</span>
            </label>
          </div>
        </CardContent>
      </Card>

      {/* Step 2: Card Input */}
      {state.step >= 2 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Enter your card pool</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block mb-2">Upload a .txt file:</label>
              <input
                type="file"
                accept=".txt"
                onChange={handleFileUpload}
                className="block w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
            </div>
            <div>
              <label className="block mb-2">Or enter cards manually (one per line):</label>
              <textarea
                value={state.cardList}
                onChange={(e) => setState(prev => ({ ...prev, cardList: e.target.value }))}
                className="w-full h-32 p-2 border rounded"
                placeholder="1x Card Name&#10;2x Another Card"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Commander Selection (if EDH) */}
      {state.step >= 2 && state.format === 'commander' && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Commander Selection</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block mb-2">Enter commander name:</label>
              <input
                type="text"
                value={state.commanderName}
                onChange={(e) => handleCommanderInput(e, false)}
                className="w-full p-2 border rounded"
                placeholder="Enter commander name"
              />
            </div>
            
            {state.hasPartnerAbility && (
              <div>
                <label className="block mb-2">Partner Commander (optional):</label>
                <input
                  type="text"
                  value={state.partnerCommander}
                  onChange={(e) => handleCommanderInput(e, true)}
                  className="w-full p-2 border rounded"
                  placeholder="Enter partner commander name"
                />
              </div>
            )}

            <div>
              <label className="block mb-2">Deck Strategy/Goals:</label>
              <textarea
                value={state.deckGoal}
                onChange={(e) => setState(prev => ({ ...prev, deckGoal: e.target.value }))}
                className="w-full h-32 p-2 border rounded"
                placeholder="Describe your deck strategy and goals..."
              />
            </div>

            <button
              onClick={handleBuildDeck}
              disabled={state.loading || !state.cardList || !state.commanderName}
              className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:bg-gray-400"
            >
              Build Deck
            </button>
          </CardContent>
        </Card>
      )}

      {/* Loading State */}
      {state.loading && (
        <div className="flex justify-center items-center p-4">
          <Loader2 className="h-8 w-8 animate-spin" />
          <span className="ml-2">Processing...</span>
        </div>
      )}

      {/* Results Display */}
      {state.result && (
        <Card>
          <CardHeader>
            <CardTitle>Your Optimized Deck</CardTitle>
          </CardHeader>
          <CardContent>
            {renderDeckList()}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default DeckBuilder;