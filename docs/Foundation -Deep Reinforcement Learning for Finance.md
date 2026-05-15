# Deep Reinforcement Learning for Finance — Bản nhập môn

> Mục tiêu: đọc bản này trước để hiểu “bức tranh lớn”, sau đó mới đọc file `Deep Reinforcement Learning for Finance - Deep Understanding.md`.

---

## 1. Nói cực ngắn: chủ đề này là gì?

**Deep Reinforcement Learning for Finance** là cách dạy máy tự học cách ra quyết định tài chính.

Ví dụ:

- hôm nay nên mua cổ phiếu nào?
- nên bán bao nhiêu?
- nên giữ tiền mặt hay mua thêm?
- nên chia vốn giữa nhiều cổ phiếu ra sao?
- khi thị trường sập thì nên làm gì?

Máy không chỉ học “giá ngày mai tăng hay giảm”. Máy học **hành động nào giúp kiếm tiền tốt hơn và giảm rủi ro hơn theo thời gian**.

---

## 2. Ví dụ đời thường trước

Hãy tưởng tượng bạn chơi một game đầu tư.

Mỗi ngày bạn thấy:

- giá cổ phiếu;
- bạn đang có bao nhiêu tiền;
- bạn đang giữ bao nhiêu cổ phiếu;
- thị trường đang bình thường hay hoảng loạn.

Mỗi ngày bạn được chọn:

- mua;
- bán;
- giữ nguyên.

Sau đó game cho điểm:

- nếu tài khoản tăng: điểm cộng;
- nếu tài khoản giảm: điểm trừ;
- nếu giao dịch quá nhiều: bị trừ phí;
- nếu rủi ro quá cao: bị phạt thêm.

Sau rất nhiều ván, bạn học được kiểu:

- khi thị trường ổn và cổ phiếu đang có xu hướng tốt → mua thêm;
- khi thị trường nhiễu → giảm vị thế;
- khi có dấu hiệu khủng hoảng → bán bớt, giữ tiền mặt;
- không giao dịch liên tục vì phí ăn mất lợi nhuận.

DRL làm chuyện tương tự, nhưng bằng thuật toán và dữ liệu.

---

## 3. Vì sao không chỉ dùng AI dự đoán giá?

Dự đoán giá là câu hỏi:

> “Ngày mai giá tăng hay giảm?”

Nhưng đầu tư thật cần câu hỏi khác:

> “Tôi nên làm gì với tiền của mình?”

Hai câu này khác nhau.

Ví dụ:

- Model dự đoán cổ phiếu A tăng 1%.
- Nhưng phí giao dịch là 0.2%.
- Rủi ro cổ phiếu A rất cao.
- Bạn đang có quá nhiều A rồi.

Vậy có nên mua thêm không? Chưa chắc.

Finance không chỉ cần dự đoán đúng. Finance cần quyết định tốt sau khi tính:

- lợi nhuận;
- rủi ro;
- phí giao dịch;
- số tiền đang có;
- cổ phiếu đang giữ;
- thị trường đang ở trạng thái nào.

Đây là lý do Reinforcement Learning hợp với finance.

---

## 4. Reinforcement Learning là gì?

Reinforcement Learning, viết tắt là RL, là học bằng thử và nhận phản hồi.

Công thức đời thường:

```text
thấy tình huống → chọn hành động → nhận kết quả → học từ kết quả
```

Ví dụ học lái xe:

- thấy đèn đỏ;
- đạp phanh;
- không bị tai nạn;
- học rằng đèn đỏ thì nên dừng.

Ví dụ học đầu tư:

- thấy thị trường đang giảm mạnh;
- bán bớt cổ phiếu;
- tài khoản giảm ít hơn thị trường;
- học rằng lúc khủng hoảng nên giảm rủi ro.

---

## 5. Deep Reinforcement Learning khác RL thường ở đâu?

RL thường có thể dùng bảng đơn giản để nhớ:

```text
nếu gặp tình huống A → làm hành động B
```

Nhưng finance quá phức tạp:

- hàng trăm cổ phiếu;
- nhiều chỉ báo;
- nhiều ngày lịch sử;
- nhiều kiểu rủi ro;
- nhiều điều kiện thị trường.

Không thể lưu hết bằng bảng đơn giản.

**Deep Reinforcement Learning** dùng neural network để học từ dữ liệu lớn và tình huống phức tạp.

Nói dễ hiểu:

- RL = cách học qua thử và nhận thưởng/phạt.
- Deep Learning = bộ não mạng neural để xử lý dữ liệu phức tạp.
- DRL = dùng mạng neural để học cách ra quyết định qua thưởng/phạt.

---

## 6. Bốn chữ quan trọng nhất

Bạn chỉ cần hiểu 4 chữ này trước:

```text
State → Action → Reward → Policy
```

### State — tình huống hiện tại

State là những gì máy nhìn thấy.

Trong finance, state có thể là:

- giá cổ phiếu hôm nay;
- giá vài ngày trước;
- tiền mặt còn lại;
- số cổ phiếu đang giữ;
- phí giao dịch;
- chỉ báo thị trường;
- mức biến động;
- tin tức;
- dữ liệu order book.

Nói ngắn: **state = bối cảnh ra quyết định**.

### Action — hành động

Action là điều máy làm.

Ví dụ:

- mua 10 cổ phiếu;
- bán 5 cổ phiếu;
- giữ nguyên;
- chuyển 30% vốn sang cổ phiếu A;
- đặt giá mua thấp hơn thị trường;
- hedge option bằng underlying.

Nói ngắn: **action = quyết định tài chính**.

### Reward — điểm thưởng/phạt

Reward là cách chấm điểm hành động.

Ví dụ đơn giản:

```text
reward = tài khoản hôm nay - tài khoản hôm qua - phí giao dịch
```

Nếu tài khoản tăng sau phí → reward dương.  
Nếu tài khoản giảm → reward âm.

Nhưng thực tế reward nên tính thêm rủi ro:

```text
reward = lợi nhuận - phí giao dịch - phạt rủi ro - phạt drawdown
```

Nói ngắn: **reward = thứ máy cố tối đa hóa**.

### Policy — chiến lược

Policy là chiến lược máy học được.

Ví dụ:

- nếu cổ phiếu mạnh, thị trường ổn, rủi ro thấp → mua;
- nếu đang giữ quá nhiều một mã → không mua thêm;
- nếu thị trường biến động mạnh → giảm vị thế;
- nếu phí quá cao → giao dịch ít lại.

Nói ngắn: **policy = luật ra quyết định đã học**.

---

## 7. Một vòng học đầy đủ

Một ngày giao dịch có thể diễn ra như sau:

```text
1. Máy nhìn thị trường hôm nay.
2. Máy biết đang có bao nhiêu tiền và cổ phiếu.
3. Máy chọn mua/bán/giữ.
4. Thị trường sang ngày mai.
5. Tài khoản tăng hoặc giảm.
6. Máy nhận reward.
7. Máy điều chỉnh chiến lược.
8. Lặp lại hàng nghìn lần.
```

Mục tiêu cuối cùng:

```text
học chiến lược tạo lợi nhuận tốt nhưng không chịu rủi ro quá lớn
```

---

## 8. Finance có những bài toán nào dùng DRL?

### 8.1. Stock trading

Máy học mua/bán/giữ cổ phiếu.

Ví dụ:

- chọn 30 cổ phiếu Dow Jones;
- mỗi ngày quyết định mua/bán bao nhiêu;
- mục tiêu tăng giá trị tài khoản;
- so với chỉ số DJIA hoặc chiến lược truyền thống.

Đây là bài dễ hình dung nhất.

### 8.2. Portfolio management

Không chỉ mua một cổ phiếu, mà chia vốn giữa nhiều tài sản.

Ví dụ:

```text
40% cổ phiếu A
25% cổ phiếu B
20% trái phiếu
15% tiền mặt
```

Máy học cách đổi tỷ trọng theo thời gian.

Mục tiêu:

- tăng lợi nhuận;
- giảm biến động;
- giảm drawdown;
- không giao dịch quá nhiều.

### 8.3. Optimal execution

Bạn đã quyết định mua/bán một lượng lớn cổ phiếu. Vấn đề là bán/mua sao cho ít tốn chi phí nhất.

Ví dụ:

Bạn cần bán 1 triệu cổ phiếu.

Nếu bán một lần:

- thị trường thấy lệnh lớn;
- giá bị đẩy xuống;
- bạn bán được giá xấu.

Optimal execution hỏi:

> Nên chia lệnh này thành bao nhiêu phần, đặt lúc nào, giá nào, để giảm thiệt hại?

Ở đây DRL không tìm “cổ phiếu nào ngon”. Nó tìm **cách khớp lệnh tốt nhất**.

### 8.4. Market making

Market maker đặt cả giá mua và giá bán.

Ví dụ:

```text
mua ở 99.9
bán ở 100.1
ăn chênh lệch 0.2
```

Nhưng rủi ro là:

- ôm quá nhiều hàng;
- bị giá chạy ngược;
- bị người khác giao dịch khi họ biết nhiều hơn mình.

DRL giúp học cách đặt bid/ask và kiểm soát hàng tồn.

### 8.5. Option hedging

Khi bán hoặc giữ option, bạn cần hedge rủi ro bằng tài sản cơ sở.

Ví dụ:

- bạn có option liên quan đến cổ phiếu A;
- giá A và volatility thay đổi liên tục;
- bạn phải mua/bán A để giữ rủi ro trong mức chấp nhận được.

DRL học cách hedge sao cho:

- giảm rủi ro;
- không giao dịch quá nhiều;
- giảm phí.

---

## 9. Ba thuật toán hay gặp, hiểu kiểu đời thường

Bạn sẽ thấy nhiều tên như DQN, PPO, A2C, DDPG. Chưa cần hiểu công thức sâu. Hiểu vai trò trước.

### DQN

DQN hợp khi hành động ít và rời rạc.

Ví dụ:

```text
mua / bán / giữ
```

Nó học kiểu:

```text
trong tình huống này, hành động nào có điểm cao nhất?
```

Hạn chế: nếu có 30 cổ phiếu và mỗi cổ phiếu có nhiều số lượng mua/bán, số hành động nổ rất lớn.

### DDPG

DDPG hợp với hành động liên tục.

Ví dụ:

```text
mua 12.7% vốn vào cổ phiếu A
bán 4.3% cổ phiếu B
```

Finance thường cần hành động liên tục, nên DDPG hay xuất hiện.

### PPO

PPO là thuật toán học chính sách khá ổn định.

Ý tưởng đơn giản:

> Cập nhật chiến lược từng bước vừa phải, không nhảy quá mạnh.

Điều này quan trọng vì trong finance, cập nhật quá mạnh dễ làm strategy bất ổn.

### A2C

A2C có hai phần:

- một phần chọn hành động;
- một phần đánh giá hành động đó tốt hay xấu.

Nó thường ổn định và có thể kiểm soát rủi ro tốt hơn trong vài thiết lập.

---

## 10. Vì sao paper dùng ensemble PPO/A2C/DDPG?

Không thuật toán nào thắng mọi thị trường.

Ví dụ:

- thị trường tăng mạnh: một thuật toán thích theo trend có thể tốt;
- thị trường giảm: thuật toán thận trọng hơn có thể tốt;
- thị trường biến động: thuật toán kiểm soát rủi ro có thể tốt.

Vì vậy paper dùng ensemble:

```text
train PPO, A2C, DDPG
↓
kiểm tra thuật toán nào có Sharpe tốt nhất gần đây
↓
dùng thuật toán đó trade giai đoạn tiếp theo
```

Nói dễ hiểu:

> Có 3 trader máy. Mỗi quý xem trader nào đang làm tốt nhất sau khi tính rủi ro, rồi giao tiền cho trader đó.

---

## 11. Sharpe ratio là gì?

Sharpe ratio là thước đo:

```text
lợi nhuận kiếm được / rủi ro chịu đựng
```

Hai chiến lược:

```text
A: lời 20%, biến động rất mạnh
B: lời 15%, biến động thấp hơn nhiều
```

Chiến lược B có thể tốt hơn nếu tính theo Sharpe.

Trong finance, không chỉ hỏi:

> Kiếm được bao nhiêu?

Mà phải hỏi:

> Kiếm được bao nhiêu trên mỗi đơn vị rủi ro?

---

## 12. Drawdown là gì?

Drawdown là mức tài khoản rơi từ đỉnh xuống đáy.

Ví dụ:

```text
Tài khoản lên 100,000 USD
Sau đó rơi xuống 70,000 USD
Drawdown = -30%
```

Một chiến lược có return cao nhưng drawdown quá sâu có thể không chịu nổi về tâm lý và rủi ro.

Vì vậy đọc paper DRL finance phải nhìn:

- return;
- Sharpe ratio;
- volatility;
- max drawdown;
- phí giao dịch;
- turnover.

Không nhìn mỗi lợi nhuận.

---

## 13. Transaction cost và slippage quan trọng cỡ nào?

Rất quan trọng.

Nếu backtest bỏ qua phí, strategy có thể đẹp giả.

Ví dụ:

```text
mỗi ngày lời 0.1%
nhưng phí mua/bán tổng cộng 0.2%
```

Nhìn trước phí thì lời.  
Sau phí thì lỗ.

Slippage là khi bạn muốn mua giá 100 nhưng khớp thật ở 100.1 hoặc 100.2.

Trong giao dịch thật, đặc biệt với lệnh lớn:

- không phải lúc nào cũng khớp đúng giá mong muốn;
- không phải lúc nào cũng khớp hết lệnh;
- lệnh của bạn có thể tự làm giá xấu đi.

Đây là lý do nhiều backtest DRL không đáng tin nếu bỏ qua slippage.

---

## 14. Rủi ro lớn nhất của DRL trong finance

### 14.1. Overfitting

Máy học quá kỹ dữ liệu quá khứ, nhưng không dùng được tương lai.

Giống học thuộc đáp án đề cũ, gặp đề mới thì sai.

### 14.2. Thị trường thay đổi

Chiến lược thắng giai đoạn 2016-2019 có thể fail năm 2020 hoặc 2022.

Thị trường có nhiều chế độ:

- tăng ổn định;
- giảm mạnh;
- đi ngang;
- khủng hoảng;
- lãi suất tăng;
- thanh khoản thấp.

### 14.3. Reward sai

Nếu reward chỉ là lợi nhuận ngắn hạn, máy có thể học hành vi nguy hiểm:

- dùng rủi ro quá cao;
- giao dịch quá nhiều;
- gom tail risk;
- né giao dịch để giảm volatility giả.

### 14.4. Môi trường giả

Nếu simulator không giống thị trường thật, agent học sai.

Ví dụ simulator cho phép bán 1 triệu cổ phiếu tại giá đóng cửa mà không làm giá giảm. Thị trường thật không như vậy.

### 14.5. Khó giải thích

Deep model thường là hộp đen.

Trong tài chính, người quản lý rủi ro sẽ hỏi:

> Vì sao model mua cổ phiếu này? Vì sao tăng vị thế lúc thị trường xấu?

Nếu không giải thích được, khó deploy thật.

---

## 15. Cách đọc bản Deep Understanding sau file này

Khi đọc bản deep, đừng cố hiểu mọi thuật ngữ ngay. Đọc theo thứ tự này:

### Lượt 1: đọc để nắm bức tranh

Tập trung các mục:

- Tầng 1 — Bản chất;
- Tầng 2 — Nguyên nhân;
- Feynman Test;
- Bản đồ tư duy ngắn.

Bỏ qua công thức nếu thấy nặng.

### Lượt 2: đọc để hiểu cơ chế

Tập trung:

- State;
- Action;
- Reward;
- Policy;
- DDPG;
- Ensemble PPO/A2C/DDPG.

### Lượt 3: đọc để hiểu ứng dụng

Tập trung 4 bài toán:

- Portfolio selection;
- Optimal execution;
- Option hedging;
- Market making.

### Lượt 4: đọc để biết cái gì dễ sai

Tập trung:

- Edge cases;
- Trade-off;
- Phê phán;
- Câu hỏi mở.

---

## 16. Bảng dịch thuật ngữ sang nghĩa dễ hiểu

| Thuật ngữ                                | Hiểu đơn giản                                         |
| ---------------------------------------- | ----------------------------------------------------- |
| Agent                                    | Người/máy ra quyết định.                              |
| Environment                              | Thị trường hoặc game đầu tư.                          |
| State                                    | Tình huống hiện tại máy thấy.                         |
| Action                                   | Hành động máy chọn.                                   |
| Reward                                   | Điểm thưởng/phạt sau hành động.                       |
| Policy                                   | Chiến lược máy học được.                              |
| Portfolio                                | Rổ tài sản đang nắm giữ.                              |
| Holdings                                 | Số cổ phiếu/tài sản đang giữ.                         |
| Cash balance                             | Tiền mặt còn lại.                                     |
| Return                                   | Lợi nhuận.                                            |
| Volatility                               | Mức biến động.                                        |
| Sharpe ratio                             | Lợi nhuận so với rủi ro.                              |
| Drawdown                                 | Mức sụt giảm từ đỉnh tài khoản.                       |
| Transaction cost                         | Phí giao dịch.                                        |
| Slippage                                 | Giá khớp thật xấu hơn giá mong muốn.                  |
| Market impact                            | Lệnh của mình làm ảnh hưởng giá.                      |
| Backtest                                 | Thử chiến lược trên dữ liệu quá khứ.                  |
| Overfitting                              | Học thuộc quá khứ, fail tương lai.                    |
| DQN(Deep Q-Network)                      | Thuật toán hợp hành động rời rạc.                     |
| DDPG(Deep Deterministic Policy Gradient) | Thuật toán hợp hành động liên tục.                    |
| PPO(Proximal Policy Optimization)        | Thuật toán cập nhật chính sách ổn định.               |
| A2C(Advantage Actor-Critic)              | Thuật toán vừa chọn hành động vừa đánh giá hành động. |
| Ensemble                                 | Kết hợp nhiều model/agent.                            |
| Market making                            | Đặt giá mua/bán để kiếm spread.                       |
| Optimal execution                        | Khớp lệnh lớn sao cho ít tốn chi phí.                 |
| Option hedging                           | Điều chỉnh vị thế để giảm rủi ro option.              |

---

## 17. Checklist: tôi đã đủ nền để đọc bản deep chưa?

Bạn nên đọc bản deep khi trả lời được mấy câu này:

- [ ] DRL khác dự đoán giá ở đâu?
- [ ] State là gì trong bài toán trading?
- [ ] Action có thể là gì?
- [ ] Reward dùng để làm gì?
- [ ] Vì sao phí giao dịch làm backtest đẹp thành vô nghĩa?
- [ ] Sharpe ratio khác return ở đâu?
- [ ] Drawdown là gì?
- [ ] Vì sao thị trường thay đổi làm model dễ fail?
- [ ] Vì sao action liên tục quan trọng trong portfolio management?
- [ ] Vì sao market making khác stock trading bình thường?

Nếu chưa trả lời được, đọc lại phần 4–14.

---

## 18. Tóm tắt một câu

DRL for Finance là cách dạy máy học chiến lược tài chính qua vòng lặp nhìn thị trường, chọn hành động, nhận thưởng/phạt, rồi cải thiện dần; sức mạnh nằm ở tối ưu quyết định dài hạn, còn rủi ro lớn nằm ở reward sai, backtest giả, phí giao dịch, overfitting và thị trường đổi chế độ.

---

_Last updated: 09/05/2026_

---

## Graph links

- [[DRL Finance - Graph Map]]
- [[Deep Understanding - Deep Reinforcement Learning for Finance]]
- [[Paper - DDPG Stock Trading]]
- [[Paper - Ensemble Stock Trading]]
- [[Survey - RL Finance Applications 2025]]
- [[Survey - Intelligent Investment Decision Making 2025]]
- [[Survey - Evolution of RL in Quantitative Finance 2025]]
