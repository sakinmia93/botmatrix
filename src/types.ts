export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  plan?: string;
  points?: number;
  telegramConnected?: boolean;
  telegramUsername?: string;
  isAdmin?: boolean;
}

export type BotStatus = 'working' | 'stopped' | 'cloned' | 'transferred';

export interface BotCommand {
  id: string;
  name: string;
  code: string;
  isPinned?: boolean;
  isAdminOnly?: boolean;
  aliases?: string[];
  folder?: string;
  updatedAt?: string;
}

export interface EnvVariable {
  id: string;
  key: string;
  value: string;
  raw?: boolean;
}

export interface BotErrorLog {
  id: string;
  time: string;
  command: string;
  message: string;
  stack?: string;
}

export interface BotItem {
  id: string;
  botNumericId: string;
  username: string;
  name: string;
  status: BotStatus;
  activeUsers: number;
  totalCommands: number;
  category: string;
  lastActive: string;
  uptime: string;
  version: string;
  folder?: string;
  isPinned?: boolean;
  photoUrl?: string;
  webhookUrl?: string;
  token?: string;
  tokenMasked?: string;
  hasToken?: boolean;
  inRecycleBin?: boolean;
  deletedAt?: string;
  commands?: BotCommand[];
  envVars?: EnvVariable[];
  fasterResponse?: boolean;
  autoTranslate?: boolean;
  miniAppUrl?: string;
  miniAppTitle?: string;
  errors?: BotErrorLog[];
  chats?: BotChatUser[];
  description?: string;
  createdAt?: string;
}

export interface BotChatUser {
  id: string;
  telegramId: string;
  name: string;
  username: string;
  avatarColor?: string;
  photoUrl?: string;
  lastActive: string;
  lastMessage?: string;
  isBlocked: boolean;
  messagesCount?: number;
  languageCode?: string;
  firstSeen?: string;
  botBlocked?: boolean;
}

export interface ActivityHourData {
  time: string;
  ts?: string;
  users: number; // 0 to 3 scale as in user prompt
  commands: number;
}

export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  time: string;
  read: boolean;
  type: 'info' | 'success' | 'warning' | 'alert';
  link?: string;
}

export type PageTab = 
  | 'Dashboard'
  | 'My Bots'
  | 'Bot Store'
  | 'Plans & Billing'
  | 'Broadcast Manager'
  | 'Recycle Bin'
  | 'Transfers'
  | 'Settings'
  | 'Notifications'
  | 'Help'
  | 'Support'
  | 'Admin';

export type BotStudioTab =
  | 'Intro'
  | 'Commands'
  | 'Search'
  | 'Errors'
  | 'Manage'
  | 'Chats'
  | 'Database'
  | 'Admin'
  | 'Settings';

export type TelegramButtonType =
  | 'url'
  | 'callback_data'
  | 'web_app'
  | 'switch_inline_query'
  | 'switch_inline_query_current_chat'
  | 'copy_text'
  | 'request_chat';

export interface InlineButton {
  id: string;
  text: string;
  type?: TelegramButtonType;
  url?: string;
  callbackData?: string;
  webAppUrl?: string;
  switchInlineQuery?: string;
  copyText?: string;
  row?: number;
  style?: 'primary' | 'success' | 'danger';
  iconEmojiId?: string;
}

export interface ActiveSessionItem {
  id: string;
  device: string;
  browser: string;
  os: string;
  ip: string;
  location: string;
  isCurrent: boolean;
  status: 'online' | 'offline';
  lastActive: string;
  clientType: 'desktop' | 'mobile' | 'web';
}

export interface TransferHistoryRecord {
  id: string;
  botId: string;
  botName: string;
  botNumericId: string;
  type: 'incoming' | 'outgoing';
  sender: string;
  recipient: string;
  date: string;
  relativeTime: string;
  status: 'completed' | 'pending' | 'cancelled' | 'expired';
  tokenHash: string;
  commandsCount: number;
  foldersCount: number;
}

export interface PlatformSettings {
  email: string;
  apiKey: string;
  apiKeyMasked?: string; // e.g. "BMP-xxxx••••••••" — shown once the raw key is no longer held in memory
  apiKeyCreatedAt: string;
  transferConfig: 'whitelist_auto' | 'whitelist_only' | 'open' | 'disabled';
  senderWhitelist: string[];
  outgoingLimit: number; // bots per 10 minutes (max 50)
  allowBotCodeToDeleteBots: boolean;
  globalBotAdmins: string[];
  activeSessions: ActiveSessionItem[];
  emailNotifications: boolean;
  notificationsEnabled?: boolean;
  browserPopups?: boolean;
  notificationTypes?: Record<string, boolean>;
  disableAnimations: boolean;
  minBroadcastUsers?: number;
  plan: {
    name: string;
    remainingPoints: number;
    extraPoints: number;
    resetsOn: string;
    changePlanTg: string;
    billingSupportTg: string;
  };
}

export interface FailedBroadcastRecipient {
  id: string;
  telegramId: string;
  name: string;
  username?: string;
  reason: string;
  failedAt: string;
}

export interface BotBroadcastStats {
  botId: string;
  botName: string;
  botUsername: string;
  targetCount: number;
  sentCount: number;
  failedCount: number;
  status: 'Delivering' | 'Done' | 'Paused' | 'Failed' | 'Cancelled';
  speed: string;
  elapsedSeconds?: number;
}

export interface BroadcastItem {
  id: string;
  trackId?: string;
  title: string;
  targetBotIds: string[];
  targetBotUsernames: string[];
  messageType: 'Text' | 'Photo' | 'Video' | 'Audio' | 'Doc' | 'GIF' | 'Voice' | 'VidNote' | 'Sticker' | 'Location' | 'Venue' | 'Contact' | 'Poll' | 'Dice' | 'Forward';
  messageText: string;
  mediaSource?: '' | 'upload' | 'url';
  mediaName?: string;
  mediaUrl?: string;
  parseMode: 'None' | 'HTML' | 'Markdown' | 'MarkdownV2';
  inlineButtons: InlineButton[];
  languageFilter?: string;
  status: 'Active' | 'Done' | 'Failed' | 'Paused' | 'Completed' | 'Cancelled';
  sentCount: number;
  totalTargetUsers: number;
  targetUserLimit?: number;
  inProgressCount?: number;
  failedCount?: number;
  blockedCount?: number;
  remainingCount?: number;
  percent?: number;
  ratePerSec?: number;
  etaSeconds?: number | null;
  finishedAt?: string | null;
  failedRecipients?: FailedBroadcastRecipient[];
  cleanedFailed?: boolean;
  unreachableCount?: number;
  cleanedCount?: number;
  reasons?: { reason: string; kind: 'unreachable' | 'error'; count: number }[];
  deliverySpeed?: string;
  botStats?: BotBroadcastStats[];
  createdAt: string;
  startedAt?: string;
  elapsedSeconds?: number;
  completedAt?: string;
}

export interface TransferRequest {
  id: string;
  botId: string;
  botName: string;
  botUsername: string;
  commandsCount: number;
  foldersCount: number;
  type: 'incoming' | 'outgoing';
  senderEmail?: string;
  recipientEmail?: string;
  status: 'pending' | 'accepted' | 'rejected' | 'cancelled';
  createdAt: string;
  expiresAt: string;
}

export interface StoreBot {
  id: string;
  name: string;
  author: string;
  authorEmail: string;
  authorType?: string;
  clones: number;
  stars: number;
  version: string;
  category: string;
  tags: string[];
  shortDesc: string;
  about: string;
  keyFeatures: string[];
  isVerified?: boolean;
  price?: number;
  priceDisplay?: string;
  aiOverview: {
    summary: string;
    faqs: { question: string; answer: string }[];
  };
  similarBots?: {
    id: string;
    name: string;
    category: string;
    subcategory: string;
    clones: number;
    stars: number;
  }[];
  botPayload: Partial<BotItem>;
}


