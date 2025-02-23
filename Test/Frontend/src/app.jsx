import React from 'react';
import Header from './components/Header';
import DeckBuilder from './components/DeckBuilder';

const App = () => {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="container mx-auto py-6">
        <DeckBuilder />
      </main>
    </div>
  );
};

export default App;