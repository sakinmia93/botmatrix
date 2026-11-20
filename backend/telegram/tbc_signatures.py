"""Positional parameter order for Bot API methods (from the TBC TPY method index).

Lets `bot.sendGift(1, 2)` style positional calls map onto Telegram parameters for
methods that BotWrapper has no special handling for. Methods absent here still work
with keyword arguments (BotWrapper forwards any method name to Telegram)."""

_RAW = """
createInvoiceLink: title description payload provider_token currency prices
refundStarPayment: user_id telegram_payment_charge_id
answerShippingQuery: shipping_query_id ok shipping_options error_message
answerPreCheckoutQuery: pre_checkout_query_id ok error_message
getUpdates: offset limit timeout allowed_updates
getWebhookInfo:
deleteMessageReaction: chat_id message_id user_id actor_chat_id
deleteAllMessageReactions: chat_id user_id actor_chat_id
getUserProfilePhotos: user_id offset limit
getUserProfileAudios: user_id offset limit
getUserPersonalChatMessages: user_id limit
setMyProfilePhoto: photo
removeMyProfilePhoto:
getChatMembersCount: chat_id
setChatMemberTag: chat_id user_id tag
sendRichMessageDraft: draft_id rich_message message_thread_id chat_id
sendMessageDraft: draft_id text message_thread_id parse_mode entities chat_id
sendLivePhoto: live_photo photo business_connection_id message_thread_id direct_messages_topic_id caption parse_mode caption_entities show_caption_above_media has_spoiler disable_notification protect_content allow_paid_broadcast message_effect_id suggested_post_parameters reply_parameters reply_markup chat_id
sendChecklist: business_connection_id checklist disable_notification protect_content message_effect_id reply_parameters reply_markup chat_id
editMessageChecklist: business_connection_id message_id checklist reply_markup chat_id
getMyStarBalance:
editUserStarSubscription: user_id telegram_payment_charge_id is_canceled
savePreparedInlineMessage: user_id result allow_user_chats allow_bot_chats allow_group_chats allow_channel_chats
savePreparedKeyboardButton: user_id button
answerGuestQuery: guest_query_id result
answerChatJoinRequestQuery: chat_join_request_query_id result
sendChatJoinRequestWebApp: chat_join_request_query_id web_app_url
getAvailableGifts:
sendGift: gift_id user_id chat_id pay_for_upgrade text text_parse_mode text_entities
giftPremiumSubscription: user_id month_count star_count text text_parse_mode text_entities
getUserGifts: user_id exclude_unlimited exclude_limited_upgradable exclude_limited_non_upgradable exclude_from_blockchain exclude_unique sort_by_price offset limit
getChatGifts: chat_id exclude_unsaved exclude_saved exclude_unlimited exclude_limited_upgradable exclude_limited_non_upgradable exclude_from_blockchain exclude_unique sort_by_price offset limit
getBusinessAccountGifts: business_connection_id exclude_unsaved exclude_saved exclude_unlimited exclude_limited_upgradable exclude_limited_non_upgradable exclude_unique exclude_from_blockchain sort_by_price offset limit
convertGiftToStars: business_connection_id owned_gift_id
upgradeGift: business_connection_id owned_gift_id keep_original_details star_count
transferGift: business_connection_id owned_gift_id new_owner_chat_id star_count
verifyUser: user_id custom_description
verifyChat: chat_id custom_description
removeUserVerification: user_id
removeChatVerification: chat_id
setUserEmojiStatus: user_id emoji_status_custom_emoji_id emoji_status_expiration_date
setPassportDataErrors: user_id errors
readBusinessMessage: business_connection_id chat_id message_id
deleteBusinessMessages: business_connection_id message_ids
setBusinessAccountName: business_connection_id first_name last_name
setBusinessAccountUsername: business_connection_id username
setBusinessAccountBio: business_connection_id bio
setBusinessAccountProfilePhoto: business_connection_id photo is_public
removeBusinessAccountProfilePhoto: business_connection_id is_public
setBusinessAccountGiftSettings: business_connection_id show_gift_button accepted_gift_types
getBusinessAccountStarBalance: business_connection_id
transferBusinessAccountStars: business_connection_id star_count
postStory: business_connection_id content active_period caption parse_mode caption_entities areas post_to_chat_page protect_content
editStory: business_connection_id story_id content caption parse_mode caption_entities areas
deleteStory: business_connection_id story_id
repostStory: business_connection_id from_chat_id from_story_id active_period post_to_chat_page protect_content
approveSuggestedPost: chat_id message_id send_date
declineSuggestedPost: chat_id message_id comment
getManagedBotToken: user_id
replaceManagedBotToken: user_id
getManagedBotAccessSettings: user_id
setManagedBotAccessSettings: user_id is_access_restricted added_user_ids
"""

SIGNATURES = {}
for _l in _RAW.strip().splitlines():
    _n, _, _p = _l.partition(":")
    SIGNATURES[_n.strip().lower()] = _p.split()

ALIASES = {"getchatmemberscount": "getChatMemberCount", "setstickersetthumb": "setStickerSetThumbnail"}
