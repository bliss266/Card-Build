import React from 'react';

const Header = () => {
  return (
    <div className="bg-blue-600 text-white p-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-2">MTG Deck Builder</h1>
        <p className="text-lg opacity-90">
          Build optimized decks for both Standard and Commander/EDH formats.
          Upload your card pool or enter your cards, and we'll help you create
          a synergistic deck based on your goals and chosen strategy.
        </p>
      </div>
    </div>
  );
};

export default Header;