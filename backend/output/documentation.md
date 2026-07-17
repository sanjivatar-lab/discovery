# Functional Documentation

- Files analyzed: 3
- Classes: 3
- Methods: 8
- Business rules mined: 8
- Dependency edges: 18 (16 unresolved)


## Class `InventoryService` (C:\Code\Discovery\backend\tests\sample_java\InventoryService.java)

Annotations: Service

- **checkAvailability(String sku, int quantity)**
  - Flow: InventoryService.checkAvailability calls: lookupStock()
  - Rule: IF available < quantity THEN return false
- **reserveStock(String sku, int quantity)**
  - Flow: InventoryService.reserveStock calls: lookupStock(), notifyLowStock()
  - Rule: IF available - quantity < minimumStockThreshold THEN notifyLowStock(sku)
- **lookupStock(String sku)**
  - Flow: InventoryService.lookupStock calls: sku.length()
- **notifyLowStock(String sku)**
  - Flow: InventoryService.notifyLowStock calls: System.out.println()

## Class `OrderController` (C:\Code\Discovery\backend\tests\sample_java\OrderController.java)

Annotations: RestController

- **createOrder(Order order)**
  - Flow: OrderController.createOrder calls: order.getCustomerId(), order.getCustomerId().isEmpty(), order.getCustomerId(), orderService.placeOrder()
  - Rule: IF order.getCustomerId() == null || order.getCustomerId().isEmpty THEN throw new IllegalArgumentException("customerId is required")
- **getStatus(Order order)**
  - Flow: OrderController.getStatus calls: orderService.describeStatus()

## Class `OrderService` (C:\Code\Discovery\backend\tests\sample_java\OrderService.java)

Annotations: Service

- **placeOrder(Order order)**
  - Flow: OrderService.placeOrder calls: order.getQuantity(), inventoryService.checkAvailability(), order.getSku(), order.getQuantity(), order.setStatus(), paymentService.charge(), order.getCustomerId(), order.getTotal()
  - Rule: IF order == null THEN throw new IllegalArgumentException("Order must not be null")
  - Rule: IF order.getQuantity() <= 0 THEN throw new IllegalArgumentException("Quantity must be greater than zero")
  - Rule: IF !available THEN order.setStatus(OrderStatus.REJECTED)
  - Rule: IF charged THEN inventoryService.reserveStock(order.getSku(), order.getQuantity())
- **describeStatus(Order order)**
  - Flow: OrderService.describeStatus calls: order.getStatus()
  - Rule: IF order.getStatus THEN case CONFIRMED; case REJECTED; case PAYMENT_FAILED; default