package code_bridge

type Client struct {
	address string
}

func NewClient(address string) *Client {
	return &Client{address: address}
}

func (c *Client) Address() string {
	if c == nil {
		return ""
	}
	return c.address
}
