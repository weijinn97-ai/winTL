// Tiến Lên Miền Nam — Game Engine
// Rules: Southern Vietnamese card game (13 cards each, 4 players)

const SUITS = ['spade', 'club', 'diamond', 'heart'];
const RANKS = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2'];
const RANK_VALUES = {};
RANKS.forEach((r, i) => RANK_VALUES[r] = i);
const SUIT_VALUES = { spade: 0, club: 1, diamond: 2, heart: 3 };

function cardValue(card) {
  return RANK_VALUES[card.rank] * 4 + SUIT_VALUES[card.suit];
}

function cardCompare(a, b) {
  return cardValue(a) - cardValue(b);
}

function createDeck() {
  const deck = [];
  for (const suit of SUITS) {
    for (const rank of RANKS) {
      deck.push({ rank, suit, id: `${rank}_${suit}` });
    }
  }
  return deck;
}

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function deal() {
  const deck = shuffle(createDeck());
  const hands = [[], [], [], []];
  for (let i = 0; i < 52; i++) {
    hands[i % 4].push(deck[i]);
  }
  hands.forEach(h => h.sort(cardCompare));
  return hands;
}

// Find which player has 3 of spades (goes first)
function findStarter(hands) {
  for (let p = 0; p < 4; p++) {
    if (hands[p].some(c => c.rank === '3' && c.suit === 'spade')) return p;
  }
  return 0;
}

// Hand type detection
const HAND_TYPES = {
  SINGLE: 'single',
  PAIR: 'pair',
  TRIPLE: 'triple',
  QUAD: 'quad',
  STRAIGHT: 'straight',
  DOUBLE_SEQ: 'double_sequence',
  INVALID: 'invalid'
};

function classifyHand(cards) {
  if (!cards || cards.length === 0) return { type: HAND_TYPES.INVALID };
  const sorted = [...cards].sort(cardCompare);

  if (sorted.length === 1) {
    return { type: HAND_TYPES.SINGLE, rank: sorted[0].rank, high: sorted[0] };
  }

  if (sorted.length === 2) {
    if (sorted[0].rank === sorted[1].rank) {
      return { type: HAND_TYPES.PAIR, rank: sorted[0].rank, high: sorted[1] };
    }
    return { type: HAND_TYPES.INVALID };
  }

  if (sorted.length === 3) {
    if (sorted[0].rank === sorted[1].rank && sorted[1].rank === sorted[2].rank) {
      return { type: HAND_TYPES.TRIPLE, rank: sorted[0].rank, high: sorted[2] };
    }
    // 3-card straight
    if (isStraight(sorted)) {
      return { type: HAND_TYPES.STRAIGHT, length: 3, high: sorted[2] };
    }
    return { type: HAND_TYPES.INVALID };
  }

  if (sorted.length === 4) {
    if (sorted.every(c => c.rank === sorted[0].rank)) {
      return { type: HAND_TYPES.QUAD, rank: sorted[0].rank, high: sorted[3] };
    }
    if (isStraight(sorted)) {
      return { type: HAND_TYPES.STRAIGHT, length: 4, high: sorted[3] };
    }
    // 2-pair sequence (đôi thông)
    if (isDoubleSequence(sorted)) {
      return { type: HAND_TYPES.DOUBLE_SEQ, length: 4, pairs: 2, high: sorted[3] };
    }
    return { type: HAND_TYPES.INVALID };
  }

  // 5+ cards
  if (isStraight(sorted) && !sorted.some(c => c.rank === '2')) {
    return { type: HAND_TYPES.STRAIGHT, length: sorted.length, high: sorted[sorted.length - 1] };
  }
  if (isDoubleSequence(sorted)) {
    return { type: HAND_TYPES.DOUBLE_SEQ, length: sorted.length, pairs: sorted.length / 2, high: sorted[sorted.length - 1] };
  }

  return { type: HAND_TYPES.INVALID };
}

function isStraight(sorted) {
  if (sorted.length < 3) return false;
  // No 2s in straights
  if (sorted.some(c => c.rank === '2')) return false;
  for (let i = 1; i < sorted.length; i++) {
    if (RANK_VALUES[sorted[i].rank] !== RANK_VALUES[sorted[i - 1].rank] + 1) return false;
  }
  return true;
}

function isDoubleSequence(sorted) {
  if (sorted.length < 4 || sorted.length % 2 !== 0) return false;
  if (sorted.some(c => c.rank === '2')) return false;
  const pairs = [];
  for (let i = 0; i < sorted.length; i += 2) {
    if (sorted[i].rank !== sorted[i + 1].rank) return false;
    pairs.push(sorted[i]);
  }
  for (let i = 1; i < pairs.length; i++) {
    if (RANK_VALUES[pairs[i].rank] !== RANK_VALUES[pairs[i - 1].rank] + 1) return false;
  }
  return true;
}

// Can hand2 beat hand1?
function canBeat(prev, curr) {
  const p = classifyHand(prev);
  const c = classifyHand(curr);
  if (c.type === HAND_TYPES.INVALID) return false;

  // Instant wins (chặt): quad beats single 2, 3-pair-seq beats pair 2, 4-pair-seq beats any
  if (p.type === HAND_TYPES.SINGLE && p.rank === '2') {
    if (c.type === HAND_TYPES.QUAD) return true;
    if (c.type === HAND_TYPES.DOUBLE_SEQ && c.pairs >= 3) return true;
  }
  if (p.type === HAND_TYPES.PAIR && p.rank === '2') {
    if (c.type === HAND_TYPES.DOUBLE_SEQ && c.pairs >= 4) return true;
  }

  // Same type, same length
  if (p.type !== c.type) return false;
  if (p.type === HAND_TYPES.STRAIGHT || p.type === HAND_TYPES.DOUBLE_SEQ) {
    if (prev.length !== curr.length) return false;
  }

  return cardValue(c.high) > cardValue(p.high);
}

// AI: find best hand to play
function findBestPlay(hand, lastPlay, isFirstTurn, mustHave3Spade) {
  if (!lastPlay) {
    // Free turn — play smallest possible
    if (mustHave3Spade) {
      // Must include 3 of spades
      const threeSpade = hand.find(c => c.rank === '3' && c.suit === 'spade');
      if (threeSpade) {
        // Try pair of 3s
        const threes = hand.filter(c => c.rank === '3');
        if (threes.length >= 2) return threes.slice(0, 2);
        // Try straight starting with 3
        const straight = findStraightIncluding(hand, threeSpade);
        if (straight) return straight;
        return [threeSpade];
      }
    }
    return findSmallestPlay(hand);
  }

  return findBeatingPlay(hand, lastPlay);
}

function findSmallestPlay(hand) {
  if (hand.length === 0) return null;
  const sorted = [...hand].sort(cardCompare);

  // Try straight first (get rid of more cards)
  const straight = findLongestStraight(sorted);
  if (straight && straight.length >= 3) return straight;

  // Try đôi thông (3+ đôi liên tiếp) — ra nhiều bài cùng lúc
  const dseq6 = findAllDoubleSequences(sorted, 6);
  if (dseq6.length > 0) return dseq6[0];

  // Then pairs
  const pairs = findGroups(sorted, 2);
  if (pairs.length > 0) return pairs[0];

  // Single smallest
  return [sorted[0]];
}

function findBeatingPlay(hand, lastPlay) {
  const prev = classifyHand(lastPlay);
  const sorted = [...hand].sort(cardCompare);

  if (prev.type === HAND_TYPES.SINGLE) {
    // Find smallest single that beats
    const card = sorted.find(c => cardValue(c) > cardValue(prev.high));
    if (card) return [card];
  }

  if (prev.type === HAND_TYPES.PAIR) {
    const pairs = findGroups(sorted, 2);
    for (const pair of pairs) {
      if (cardValue(pair[1]) > cardValue(prev.high)) return pair;
    }
  }

  if (prev.type === HAND_TYPES.TRIPLE) {
    const triples = findGroups(sorted, 3);
    for (const triple of triples) {
      if (cardValue(triple[2]) > cardValue(prev.high)) return triple;
    }
  }

  if (prev.type === HAND_TYPES.QUAD) {
    const quads = findGroups(sorted, 4);
    for (const quad of quads) {
      if (cardValue(quad[3]) > cardValue(prev.high)) return quad;
    }
  }

  if (prev.type === HAND_TYPES.STRAIGHT) {
    const straights = findAllStraights(sorted, lastPlay.length);
    for (const s of straights) {
      if (canBeat(lastPlay, s)) return s;
    }
  }

  if (prev.type === HAND_TYPES.DOUBLE_SEQ) {
    const dseqs = findAllDoubleSequences(sorted, lastPlay.length);
    for (const ds of dseqs) {
      if (canBeat(lastPlay, ds)) return ds;
    }
  }

  // Instant win checks (chặt 2)
  if (prev.type === HAND_TYPES.SINGLE && prev.rank === '2') {
    // Tứ quý chặt con 2
    const quads = findGroups(sorted, 4);
    if (quads.length > 0) return quads[0];
    // 3 đôi thông chặt con 2
    const dseqs3 = findAllDoubleSequences(sorted, 6);
    if (dseqs3.length > 0) return dseqs3[0];
    // 4 đôi thông cũng chặt con 2
    const dseqs4 = findAllDoubleSequences(sorted, 8);
    if (dseqs4.length > 0) return dseqs4[0];
  }
  if (prev.type === HAND_TYPES.PAIR && prev.rank === '2') {
    // 4 đôi thông chặt đôi 2
    const dseqs4 = findAllDoubleSequences(sorted, 8);
    if (dseqs4.length > 0) return dseqs4[0];
  }

  return null; // Pass
}

function findGroups(sorted, size) {
  const groups = [];
  let i = 0;
  while (i <= sorted.length - size) {
    if (sorted.slice(i, i + size).every(c => c.rank === sorted[i].rank)) {
      groups.push(sorted.slice(i, i + size));
      i += size;
    } else {
      i++;
    }
  }
  return groups;
}

function findLongestStraight(sorted) {
  const unique = [];
  const used = new Set();
  for (const c of sorted) {
    if (c.rank === '2') continue;
    if (!used.has(c.rank)) {
      unique.push(c);
      used.add(c.rank);
    }
  }

  let best = null;
  for (let i = 0; i < unique.length; i++) {
    const run = [unique[i]];
    for (let j = i + 1; j < unique.length; j++) {
      if (RANK_VALUES[unique[j].rank] === RANK_VALUES[run[run.length - 1].rank] + 1) {
        run.push(unique[j]);
      } else break;
    }
    if (run.length >= 3 && (!best || run.length > best.length)) {
      best = run;
    }
  }
  return best;
}

function findAllStraights(sorted, length) {
  const noTwo = sorted.filter(c => c.rank !== '2');
  const results = [];
  const byRank = {};
  for (const c of noTwo) {
    if (!byRank[c.rank]) byRank[c.rank] = [];
    byRank[c.rank].push(c);
  }

  const rankList = RANKS.filter(r => r !== '2');
  for (let i = 0; i <= rankList.length - length; i++) {
    const run = [];
    let valid = true;
    for (let j = 0; j < length; j++) {
      const r = rankList[i + j];
      if (!byRank[r] || byRank[r].length === 0) { valid = false; break; }
      run.push(byRank[r][0]);
    }
    if (valid && run.length === length) {
      results.push(run.sort(cardCompare));
    }
  }
  return results.sort((a, b) => cardValue(a[a.length - 1]) - cardValue(b[b.length - 1]));
}

function findAllDoubleSequences(sorted, length) {
  const pairCount = length / 2;
  const noTwo = sorted.filter(c => c.rank !== '2');
  const byRank = {};
  for (const c of noTwo) {
    if (!byRank[c.rank]) byRank[c.rank] = [];
    byRank[c.rank].push(c);
  }

  const results = [];
  const rankList = RANKS.filter(r => r !== '2');
  for (let i = 0; i <= rankList.length - pairCount; i++) {
    const run = [];
    let valid = true;
    for (let j = 0; j < pairCount; j++) {
      const r = rankList[i + j];
      if (!byRank[r] || byRank[r].length < 2) { valid = false; break; }
      run.push(byRank[r][0], byRank[r][1]);
    }
    if (valid) {
      results.push(run.sort(cardCompare));
    }
  }
  return results.sort((a, b) => cardValue(a[a.length - 1]) - cardValue(b[b.length - 1]));
}

function findStraightIncluding(hand, targetCard) {
  const noTwo = hand.filter(c => c.rank !== '2').sort(cardCompare);
  const targetVal = RANK_VALUES[targetCard.rank];

  for (let start = Math.max(0, targetVal - 12); start <= targetVal; start++) {
    for (let end = targetVal; end < 12; end++) {
      const len = end - start + 1;
      if (len < 3) continue;
      const run = [];
      let valid = true;
      for (let v = start; v <= end; v++) {
        const card = noTwo.find(c => RANK_VALUES[c.rank] === v && !run.includes(c));
        if (!card) { valid = false; break; }
        run.push(card);
      }
      if (valid && run.some(c => c.id === targetCard.id)) {
        return run.sort(cardCompare);
      }
    }
  }
  return null;
}

// Rank display
function rankDisplay(rank) {
  return rank;
}

function suitSymbol(suit) {
  return { spade: '♠', club: '♣', diamond: '♦', heart: '♥' }[suit];
}

function suitColor(suit) {
  return (suit === 'diamond' || suit === 'heart') ? '#e53935' : '#222';
}

function cardLabel(card) {
  return rankDisplay(card.rank) + suitSymbol(card.suit);
}
