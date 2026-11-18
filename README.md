@startuml
left to right direction

' Актеры слева (Клиентский блок)
actor "Гость" as Guest
actor "Клиент" as Client

' Актеры справа (Сотрудники и Админ)
actor "Помощник риэлтора" as Assistant
actor "Риэлтор" as Realtor
actor "Администратор" as Admin

' Иерархия актеров
Guest <|-- Client
Assistant <|-- Realtor

rectangle "АИС Риэлторского Агентства" {

  ' ==================== РЯД 1 (Верхний ряд действий) ====================
  usecase "Просмотр страницы 'О себе'" as UC_ViewCards
  usecase "Просмотр каталога недвижимости" as UC_
  usecase "Просмотр отзывов" as UC_Reviews
  usecase "Регистрация" as UC_Registration
  
  usecase "Вход" as UC_Login
  usecase "Добавление отзывов" as UC_AddReviews 
  usecase "Управление личным профилем" as UC_ViewProfile
  usecase "Отслеживание статуса сделок" as UC_TrackDeals
  usecase "Просмотр графика показов" as UC_ViewSchedule
  usecase "Получение персональных оповещений" as UC_GetNotifications

  ' ==================== РЯД 2 (Нижний ряд действий) ====================
  usecase "Управление объектами недвижимости" as UC_Property
  usecase "Ведение базы клиентов" as UC_ClientsBase
  usecase "Ведение базы объектов недвижимости" as UC_PropertiesBase
  usecase "Загрузка шаблонов договоров" as UC_UploadContracts
  usecase "Создание договоров" as UC_CrateContracts
  usecase "Планирование встреч" as UC_Showings
  usecase "Генерация и шаблоны договоров" as UC_Contracts
  usecase "Модерация отзывов" as UC_ModerationReviwers
  
  usecase "Администрирование" as UC_Admin

  ' Принудительное выравнивание: Ряд 1 строго НАД Рядом 2
  UC_ViewCards -[hidden]down-> UC_Property
  UC_Reviews -[hidden]down-> UC_ClientsDeals
  UC_ViewProfile -[hidden]down-> UC_Showings
  UC_TrackDeals -[hidden]down-> UC_Contracts
  UC_ViewSchedule -[hidden]down-> UC_Moderation
  UC_GetNotifications -[hidden]down-> UC_Admin
}

' Связи для левых актеров (Гость и Клиент)
Guest --> UC_ViewCards
Guest --> UC_Reviews

Client --> UC_ViewProfile
Client --> UC_TrackDeals
Client --> UC_ViewSchedule
Client --> UC_GetNotifications

' Связи для правых актеров (Помощник, Риэлтор, Админ)
UC_Property <-- Assistant
UC_ClientsDeals <-- Assistant
UC_Showings <-- Assistant
UC_Contracts <-- Assistant




UC_Moderation <-- Realtor

UC_Admin <-- Admin

@endl
