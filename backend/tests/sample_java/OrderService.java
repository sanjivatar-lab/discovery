package com.example.orders;

import com.example.orders.model.Order;
import com.example.orders.model.OrderStatus;

@Service
public class OrderService {

    @Autowired
    private InventoryService inventoryService;

    @Autowired
    private PaymentService paymentService;

    public Order placeOrder(Order order) {
        if (order == null) {
            throw new IllegalArgumentException("Order must not be null");
        }
        if (order.getQuantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be greater than zero");
        }

        boolean available = inventoryService.checkAvailability(order.getSku(), order.getQuantity());
        if (!available) {
            order.setStatus(OrderStatus.REJECTED);
            return order;
        }

        boolean charged = paymentService.charge(order.getCustomerId(), order.getTotal());
        if (charged) {
            inventoryService.reserveStock(order.getSku(), order.getQuantity());
            order.setStatus(OrderStatus.CONFIRMED);
        } else {
            order.setStatus(OrderStatus.PAYMENT_FAILED);
        }

        return order;
    }

    public String describeStatus(Order order) {
        switch (order.getStatus()) {
            case CONFIRMED:
                return "Order confirmed and stock reserved";
            case REJECTED:
                return "Order rejected due to insufficient stock";
            case PAYMENT_FAILED:
                return "Order failed during payment processing";
            default:
                return "Order status unknown";
        }
    }
}
