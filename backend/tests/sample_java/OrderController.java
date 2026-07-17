package com.example.orders;

import com.example.orders.model.Order;

@RestController
public class OrderController {

    @Autowired
    private OrderService orderService;

    @PostMapping("/orders")
    public Order createOrder(Order order) {
        if (order.getCustomerId() == null || order.getCustomerId().isEmpty()) {
            throw new IllegalArgumentException("customerId is required");
        }
        return orderService.placeOrder(order);
    }

    @GetMapping("/orders/{id}/status")
    public String getStatus(Order order) {
        return orderService.describeStatus(order);
    }
}
