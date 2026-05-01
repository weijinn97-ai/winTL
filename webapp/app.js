// Tiến Lên Miền Nam — App Controller

// Game state
let gameState = {
  screen: 'login',
  username: 'Player',
  gold: 10000000,
  diamond: 0,
  currentTab: 'demla',
  gameMode: 'demla',
  betLevel: 0,

  // In-game
  hands: [[], [], [], []],
  currentPlayer: 0,
  playerIndex: 0,
  lastPlay: null,
  lastPlayBy: -1,
  passCount: 0,
  selectedCards: [],
  gameActive: false,
  isFirstTurn: true,
  turnTimer: null,
  scores: [0, 0, 0, 0],
  betAmount: 500,
};

const ROOM_CONFIGS = {
  demla: [
    { name: 'TÂN THỦ 1', bet: '500', diamond: 'x1', entry: '3.5K - 80K', minGold: 3500 },
    { name: 'TÂN THỦ 2', bet: '2K', diamond: 'x3', entry: '42K - ∞', minGold: 42000 },
    { name: 'THƯỜNG', bet: '8K', diamond: 'x10', entry: '160K - ∞', minGold: 160000 },
    { name: 'SƠ CẤP', bet: '30K', diamond: 'x30', entry: '600K - ∞', minGold: 600000 },
    { name: 'TRUNG CẤP', bet: '90K', diamond: 'x90', entry: '1.8M - ∞', minGold: 1800000 },
  ],
  nhatat: [
    { name: 'TÂN THỦ 1', bet: '3K', diamond: 'x1', entry: '3.5K - 80K', minGold: 3500 },
    { name: 'TÂN THỦ 2', bet: '10K', diamond: 'x3', entry: '42K - ∞', minGold: 42000 },
    { name: 'THƯỜNG', bet: '40K', diamond: 'x10', entry: '160K - ∞', minGold: 160000 },
    { name: 'SƠ CẤP', bet: '150K', diamond: 'x30', entry: '600K - ∞', minGold: 600000 },
    { name: 'TRUNG CẤP', bet: '450K', diamond: 'x90', entry: '1.8M - ∞', minGold: 1800000 },
    { name: 'CAO CẤP', bet: '1.5M', diamond: 'x300', entry: '6M - ∞', minGold: 6000000 },
  ],
  giaitri: [
    { name: 'THẤT LONG\nTRANH BÁ', bet: 'Free', diamond: '', entry: 'Free', minGold: 0, icon: '🏆' },
    { name: 'XÓC NGAY', bet: 'Free', diamond: '', entry: 'Free', minGold: 0, icon: '🪙' },
    { name: 'HÃY ĐỢI', bet: '???', diamond: '', entry: 'Coming soon', minGold: 0, icon: '❓' },
  ],
};

const BOT_NAMES = ['Bot Trái', 'Bot Trên', 'Bot Phải'];

// --- Screen Navigation ---
function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-' + name).classList.add('active');
  gameState.screen = name;
}

function startGuest() {
  gameState.username = 'Player' + Math.floor(Math.random() * 9000 + 1000);
  updateLobbyUI();
  showScreen('lobby');
}

function goLobby() {
  if (gameState.gameActive) {
    gameState.gameActive = false;
    clearTimeout(gameState.turnTimer);
  }
  document.getElementById('game-over').style.display = 'none';
  document.getElementById('game-menu').style.display = 'none';
  updateLobbyUI();
  showScreen('lobby');
}

function updateLobbyUI() {
  document.getElementById('lobby-username').textContent = gameState.username;
  document.getElementById('lobby-gold').textContent = formatGold(gameState.gold);
  document.getElementById('lobby-diamond').textContent = gameState.diamond;
}

function formatGold(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(2).replace(/\.?0+$/, '') + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.?0+$/, '') + 'K';
  return n.toString();
}

// --- Rooms ---
function showRooms(tab) {
  gameState.currentTab = tab || 'demla';
  document.getElementById('rooms-gold').textContent = formatGold(gameState.gold);
  document.getElementById('rooms-diamond').textContent = gameState.diamond;
  renderRoomTabs();
  renderRooms();
  showScreen('rooms');
}

function renderRoomTabs() {
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === gameState.currentTab);
  });
}

function switchTab(tab) {
  gameState.currentTab = tab;
  renderRoomTabs();
  renderRooms();
}

function renderRooms() {
  const grid = document.getElementById('rooms-grid');
  const rooms = ROOM_CONFIGS[gameState.currentTab] || [];
  grid.innerHTML = '';

  rooms.forEach((room, i) => {
    const card = document.createElement('div');
    let levelClass = 'level-' + i;
    if (gameState.currentTab === 'nhatat') levelClass = 'level-nhatat';
    if (gameState.currentTab === 'giaitri') levelClass = 'level-giaitri';

    card.className = `room-card ${levelClass}`;
    card.onclick = () => enterRoom(i);

    if (gameState.currentTab === 'giaitri') {
      card.innerHTML = `
        <div style="font-size:48px">${room.icon}</div>
        <div class="room-name" style="font-size:16px;white-space:pre-line">${room.name}</div>
      `;
    } else {
      card.innerHTML = `
        <div class="room-name">${room.name}</div>
        <div class="room-bet">Điểm Cược <strong>${room.bet}</strong></div>
        <div class="room-diamond">💎 ${room.diamond}</div>
        <div class="room-entry">👁 ${room.entry}</div>
      `;
    }

    grid.appendChild(card);
  });
}

function enterRoom(levelIndex) {
  const rooms = ROOM_CONFIGS[gameState.currentTab];
  if (!rooms || !rooms[levelIndex]) return;
  const room = rooms[levelIndex];

  if (gameState.currentTab === 'giaitri') {
    if (room.name.includes('HÃY ĐỢI')) return;
    // For entertainment modes, just start a free game
  }

  gameState.betLevel = levelIndex;
  gameState.gameMode = gameState.currentTab;
  gameState.betAmount = parseBet(room.bet);

  startGame(room);
}

function parseBet(betStr) {
  betStr = betStr.replace(/,/g, '');
  if (betStr.includes('M')) return parseFloat(betStr) * 1000000;
  if (betStr.includes('K')) return parseFloat(betStr) * 1000;
  return parseInt(betStr) || 500;
}

function quickStart() { showRooms('demla'); }
function quickStartFromRooms() {
  const rooms = ROOM_CONFIGS[gameState.currentTab];
  if (rooms && rooms.length > 0) enterRoom(0);
}
function createRoom() { showRooms('demla'); }
function joinRoom() { showRooms('demla'); }
function showShop() { }
function showSettings() { }

// --- Game ---
function startGame(room) {
  const gs = gameState;
  gs.hands = deal();
  gs.playerIndex = 0;
  gs.currentPlayer = findStarter(gs.hands);
  gs.lastPlay = null;
  gs.lastPlayBy = -1;
  gs.passCount = 0;
  gs.selectedCards = [];
  gs.gameActive = true;
  gs.isFirstTurn = true;
  gs.scores = [0, 0, 0, 0];

  document.getElementById('game-level').textContent = room.name;
  document.getElementById('game-bet').textContent = room.bet;
  document.getElementById('self-name').textContent = gs.username;
  document.getElementById('self-gold').textContent = formatGold(gs.gold);
  document.getElementById('game-over').style.display = 'none';

  showScreen('game');
  renderGame();

  // If bot starts, delay then play
  if (gs.currentPlayer !== gs.playerIndex) {
    setTimeout(() => botTurn(), 1000);
  }
}

function renderGame() {
  const gs = gameState;
  renderPlayerHand();
  renderOpponents();
  renderCenterCards();
  renderTurnIndicator();
  updateClock();
}

function renderPlayerHand() {
  const gs = gameState;
  const hand = gs.hands[gs.playerIndex];
  const container = document.getElementById('player-hand');
  container.innerHTML = '';

  hand.forEach((card, i) => {
    const el = document.createElement('div');
    const isRed = card.suit === 'diamond' || card.suit === 'heart';
    el.className = `card ${isRed ? 'red' : 'black'} ${gs.selectedCards.includes(i) ? 'selected' : ''}`;
    el.innerHTML = `
      <span class="card-rank">${card.rank}</span>
      <span class="card-suit">${suitSymbol(card.suit)}</span>
    `;
    el.onclick = () => toggleCard(i);
    container.appendChild(el);
  });

  // Show/hide action buttons
  const actions = document.getElementById('hand-actions');
  const isMyTurn = gs.currentPlayer === gs.playerIndex && gs.gameActive;
  actions.style.display = isMyTurn ? 'flex' : 'none';

  // Pass button: hide on first turn (must play)
  const btnPass = document.getElementById('btn-pass');
  btnPass.style.display = (gs.isFirstTurn && gs.lastPlay === null) ? 'none' : 'block';
}

function renderOpponents() {
  const gs = gameState;
  const slots = ['left', 'top', 'right'];
  const opponents = [1, 2, 3]; // relative to player

  opponents.forEach((offset, i) => {
    const pIdx = (gs.playerIndex + offset) % 4;
    const slot = document.getElementById('slot-' + slots[i]);
    const countEl = document.getElementById('count-' + slots[i]);
    countEl.textContent = gs.hands[pIdx].length;

    slot.querySelector('.player-name').textContent = BOT_NAMES[i];

    // Active turn highlight
    slot.classList.toggle('active-turn', gs.currentPlayer === pIdx);
  });
}

function renderCenterCards() {
  const gs = gameState;
  const container = document.getElementById('center-cards');
  container.innerHTML = '';

  if (gs.lastPlay && gs.lastPlay.length > 0) {
    gs.lastPlay.forEach(card => {
      const el = document.createElement('div');
      const isRed = card.suit === 'diamond' || card.suit === 'heart';
      el.className = `card-in-play ${isRed ? 'red' : ''}`;
      el.innerHTML = `${card.rank}<br>${suitSymbol(card.suit)}`;
      container.appendChild(el);
    });
  }
}

function renderPlayedOnSlot(slotId, cards) {
  const container = document.getElementById('played-' + slotId);
  container.innerHTML = '';

  if (!cards) {
    container.innerHTML = '<span class="pass-label">Bỏ lượt</span>';
    return;
  }

  cards.forEach(card => {
    const el = document.createElement('span');
    const isRed = card.suit === 'diamond' || card.suit === 'heart';
    el.className = `mini-card ${isRed ? 'red' : ''}`;
    el.textContent = card.rank + suitSymbol(card.suit);
    container.appendChild(el);
  });
}

function clearAllPlayedSlots() {
  ['left', 'top', 'right'].forEach(s => {
    document.getElementById('played-' + s).innerHTML = '';
  });
}

function renderTurnIndicator() {
  const gs = gameState;
  const el = document.getElementById('turn-indicator');
  if (gs.currentPlayer === gs.playerIndex) {
    el.textContent = 'Lượt của bạn!';
  } else {
    el.textContent = `${BOT_NAMES[(gs.currentPlayer - gs.playerIndex + 4) % 4 - 1]} đang suy nghĩ...`;
  }
}

function updateClock() {
  const now = new Date();
  document.getElementById('game-clock').textContent =
    now.getHours().toString().padStart(2, '0') + ':' +
    now.getMinutes().toString().padStart(2, '0');
}

// --- Player Actions ---
function toggleCard(idx) {
  const gs = gameState;
  if (gs.currentPlayer !== gs.playerIndex || !gs.gameActive) return;

  const pos = gs.selectedCards.indexOf(idx);
  if (pos === -1) {
    gs.selectedCards.push(idx);
  } else {
    gs.selectedCards.splice(pos, 1);
  }
  renderPlayerHand();
}

function playerPlay() {
  const gs = gameState;
  if (gs.currentPlayer !== gs.playerIndex || !gs.gameActive) return;
  if (gs.selectedCards.length === 0) return;

  const hand = gs.hands[gs.playerIndex];
  const cards = gs.selectedCards.map(i => hand[i]).sort(cardCompare);
  const classified = classifyHand(cards);

  if (classified.type === HAND_TYPES.INVALID) {
    showMessage('Bộ bài không hợp lệ!');
    return;
  }

  // First turn must include 3 of spades
  if (gs.isFirstTurn && gs.lastPlay === null) {
    if (!cards.some(c => c.rank === '3' && c.suit === 'spade')) {
      showMessage('Lượt đầu phải có 3♠!');
      return;
    }
  }

  // Must beat last play
  if (gs.lastPlay && !canBeat(gs.lastPlay, cards)) {
    showMessage('Phải đánh lớn hơn!');
    return;
  }

  executePlay(gs.playerIndex, cards);
}

function playerPass() {
  const gs = gameState;
  if (gs.currentPlayer !== gs.playerIndex || !gs.gameActive) return;
  if (gs.isFirstTurn && gs.lastPlay === null) return; // Can't pass on first turn

  executePass(gs.playerIndex);
}

function sortHand() {
  const gs = gameState;
  gs.hands[gs.playerIndex].sort(cardCompare);
  gs.selectedCards = [];
  renderPlayerHand();
}

// --- Game Logic ---
function executePlay(playerIdx, cards) {
  const gs = gameState;

  // Remove cards from hand
  const hand = gs.hands[playerIdx];
  cards.forEach(card => {
    const idx = hand.findIndex(c => c.id === card.id);
    if (idx !== -1) hand.splice(idx, 1);
  });

  gs.lastPlay = cards;
  gs.lastPlayBy = playerIdx;
  gs.passCount = 0;
  gs.selectedCards = [];
  gs.isFirstTurn = false;

  // Show played cards on slot
  const slotId = getSlotId(playerIdx);
  if (slotId) {
    clearAllPlayedSlots();
    renderPlayedOnSlot(slotId, cards);
  }

  showMessage(getPlayerName(playerIdx) + ' đánh ' + cards.map(cardLabel).join(' '));
  renderCenterCards();

  // Check win
  if (hand.length === 0) {
    gs.gameActive = false;
    setTimeout(() => endGame(playerIdx), 1000);
    renderGame();
    return;
  }

  nextTurn();
}

function executePass(playerIdx) {
  const gs = gameState;
  gs.passCount++;

  const slotId = getSlotId(playerIdx);
  if (slotId) renderPlayedOnSlot(slotId, null);

  showMessage(getPlayerName(playerIdx) + ' bỏ lượt');

  // If 3 passes in a row, reset - it's a free turn for last player
  if (gs.passCount >= 3) {
    gs.lastPlay = null;
    gs.lastPlayBy = -1;
    gs.passCount = 0;
    clearAllPlayedSlots();
    showMessage(getPlayerName(gs.lastPlayBy) + ' được quyền đánh tự do');
  }

  nextTurn();
}

function nextTurn() {
  const gs = gameState;
  gs.currentPlayer = (gs.currentPlayer + 1) % 4;

  // Skip players who are out
  let safety = 0;
  while (gs.hands[gs.currentPlayer].length === 0 && safety < 4) {
    gs.currentPlayer = (gs.currentPlayer + 1) % 4;
    safety++;
  }

  // If back to last player who played, free turn
  if (gs.currentPlayer === gs.lastPlayBy) {
    gs.lastPlay = null;
    gs.passCount = 0;
    clearAllPlayedSlots();
    document.getElementById('center-cards').innerHTML = '';
    showMessage(getPlayerName(gs.currentPlayer) + ' được quyền đánh tự do');
  }

  renderGame();

  if (!gs.gameActive) return;

  if (gs.currentPlayer !== gs.playerIndex) {
    // Bot's turn
    const delay = 800 + Math.random() * 800;
    gs.turnTimer = setTimeout(() => botTurn(), delay);
  }
}

function botTurn() {
  const gs = gameState;
  if (!gs.gameActive || gs.currentPlayer === gs.playerIndex) return;

  const botIdx = gs.currentPlayer;
  const hand = gs.hands[botIdx];
  const mustHave3Spade = gs.isFirstTurn && gs.lastPlay === null &&
    hand.some(c => c.rank === '3' && c.suit === 'spade');

  const play = findBestPlay(hand, gs.lastPlay, gs.isFirstTurn, mustHave3Spade);

  if (play) {
    executePlay(botIdx, play);
  } else {
    executePass(botIdx);
  }
}

function getSlotId(playerIdx) {
  const gs = gameState;
  const offset = (playerIdx - gs.playerIndex + 4) % 4;
  return ['', 'left', 'top', 'right'][offset] || null;
}

function getPlayerName(playerIdx) {
  const gs = gameState;
  if (playerIdx === gs.playerIndex) return gs.username;
  const offset = (playerIdx - gs.playerIndex + 4) % 4;
  return BOT_NAMES[offset - 1] || 'Bot';
}

function showMessage(msg) {
  document.getElementById('game-message').textContent = msg;
}

// --- End Game ---
function endGame(winnerIdx) {
  const gs = gameState;
  const overlay = document.getElementById('game-over');
  const titleEl = document.getElementById('game-over-title');
  const resultsEl = document.getElementById('game-over-results');

  const winnerName = getPlayerName(winnerIdx);
  const isPlayerWin = winnerIdx === gs.playerIndex;

  titleEl.textContent = isPlayerWin ? '🎉 Bạn thắng!' : `${winnerName} thắng!`;
  titleEl.style.color = isPlayerWin ? '#4caf50' : '#f44336';

  // Calculate scores based on remaining cards
  let html = '';
  for (let i = 0; i < 4; i++) {
    const name = getPlayerName(i);
    const remaining = gs.hands[i].length;
    let score = 0;

    if (i === winnerIdx) {
      // Winner gets bet * 3
      score = gs.betAmount * 3;
    } else {
      // Losers pay based on remaining cards
      let multiplier = remaining;
      // Instant loss multipliers
      if (remaining === 13) multiplier = 26; // Thua trắng
      else if (remaining >= 10) multiplier = remaining * 2;

      // Check for remaining 2s
      const twos = gs.hands[i].filter(c => c.rank === '2').length;
      multiplier += twos * 2;

      score = -(gs.betAmount * multiplier / 13);
    }

    score = Math.round(score);
    const isWinner = i === winnerIdx;

    html += `<div class="result-row ${isWinner ? 'winner' : ''}">
      <span class="result-name">${name}</span>
      <span class="result-cards">${remaining} lá</span>
      <span class="result-score ${score >= 0 ? 'positive' : 'negative'}">
        ${score >= 0 ? '+' : ''}${formatGold(Math.abs(score))}
      </span>
    </div>`;

    if (i === gs.playerIndex) {
      gs.gold += score;
      if (gs.gold < 0) gs.gold = 1000; // Minimum gold
    }
  }

  resultsEl.innerHTML = html;
  overlay.style.display = 'flex';
}

function playAgain() {
  document.getElementById('game-over').style.display = 'none';
  const rooms = ROOM_CONFIGS[gameState.gameMode];
  if (rooms && rooms[gameState.betLevel]) {
    startGame(rooms[gameState.betLevel]);
  }
}

// --- Game Menu ---
function showGameMenu() {
  document.getElementById('game-menu').style.display = 'flex';
}

function closeGameMenu() {
  document.getElementById('game-menu').style.display = 'none';
}

function exitGame() {
  gameState.gameActive = false;
  clearTimeout(gameState.turnTimer);
  document.getElementById('game-menu').style.display = 'none';
  goLobby();
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  showScreen('login');
});
