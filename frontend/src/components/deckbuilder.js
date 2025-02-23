import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';

const DeckBuilder = () => {
  const [commander, setCommander] = useState('');
  const [partnerCommander, setPartnerCommander] = useState('');
  const [cardList, setCardList] = useState('');
  const [deckGoal, setDeckGoal] = useState('');
  const [format, setFormat] = useState('commander'); // NEW: State for format selection
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [deck, setDeck] = useState(null);

  const buildDeck = async () => {
    try {
      setLoading(true);
      setError('');

      const response = await fetch('http://localhost:5000/api/build-deck', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          commander,
          partnerCommander,
          cardList,
          deckGoal,
          format, // NEW: Send format to backend
        }),
      });

      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error);
      }

      setDeck(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container mx-auto p-4">
      <Card className="w-full max-w-4xl mx-auto">
        <CardHeader>
          <CardTitle>MTG Deck Builder</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Commander</label>
              <input
                type="text"
                className="w-full p-2 border rounded"
                value={commander}
                onChange={(e) => setCommander(e.target.value)}
                placeholder="Enter commander name"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Partner Commander (Optional)</label>
              <input
                type="text"
                className="w-full p-2 border rounded"
                value={partnerCommander}
                onChange={(e) => setPartnerCommander(e.target.value)}
                placeholder="Enter partner commander name"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Card List</label>
              <textarea
                className="w-full p-2 border rounded h-32"
                value={cardList}
                onChange={(e) => setCardList(e.target.value)}
                placeholder="Enter card list (one card per line)"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Deck Goal</label>
              <input
                type="text"
                className="w-full p-2 border rounded"
                value={deckGoal}
                onChange={(e) => setDeckGoal(e.target.value)}
                placeholder="Enter deck goal (e.g., Aggro, Control, Combo)"
              />
            </div>

            {/* NEW: Format Selection Dropdown */}
            <div>
              <label className="block text-sm font-medium mb-1">Deck Format</label>
              <select
                className="w-full p-2 border rounded"
                value={format}
                onChange={(e) => setFormat(e.target.value)}
              >
                <option value="commander">Commander</option>
                <option value="modern">Modern</option>
                <option value="standard">Standard</option>
              </select>
            </div>

            <button
              className="w-full bg-blue-600 text-white py-2 px-4 rounded hover:bg-blue-700 disabled:opacity-50"
              onClick={buildDeck}
              disabled={loading || !commander || !cardList}
            >
              {loading ? 'Building Deck...' : 'Build Deck'}
            </button>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {deck && (
              <div className="mt-4">
                <h3 className="text-lg font-semibold mb-2">Built Deck</h3>
                <div className="space-y-2">
                  {deck.cards.map((card, index) => (
                    <div key={index} className="p-2 bg-gray-100 rounded">
                      {card.name} - {card.type} (CMC: {card.cmc})
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default DeckBuilder;
