# Questions for an engineer investigating one stored rocket landing run

Answer each question using only the viewer. For each answer give: the answer, where in the viewer you found it, and whether it is recorded, derived, from source code, or not knowable from this record. "Cannot tell from what is shown" is an acceptable answer when true.


### Q1. What was the true trajectory and outcome?
**1.1 What was the outcome, and which verdicts failed?**
**1.2 Where did the stage actually touch down?**
**1.3 What were the contact speeds, attitude, rate and propellant?**
**1.4 Describe the true trajectory shape.**

### Q2. What did the controller believe, and from which sensors?
**2.1 What did the controller receive?**
**2.2 What form does the belief take?**
**2.3 What did it believe at the end, versus the truth?**
**2.4 Which sensor carried the wrong information?**

### Q3. When did belief diverge from truth, and by how much?
**3.1 When did the divergence start?**
**3.2 By how much did they diverge?**
**3.3 In which direction was the belief wrong?**
**3.4 Did the divergence recover?**

### Q4. What decisions followed, and were they reasonable given what the controller could observe?
**4.1 When and how did the controller react?**
**4.2 What did "altimeter rejected" change?**
**4.3 Was rejecting the altimeter reasonable?**
**4.4 Were there other controller decisions of note?**

### Q5. Which requirement and safety invariant outcomes resulted, and which are measured versus inferred?
**5.1 Requirement results.**
**5.2 Invariant results.**
**5.3 Which of these are measured and which inferred?**
**5.4 Why is the outcome `hard_landing` while `invariants_pass` is true?**
**X1. What altitude did vertical guidance use at about 15 s, and did the controller "ignore" the altimeter?**
**X2. Was rejecting the altimeter "correct"?**
**X3. Did `gnss_bias` cause R5 (or R1, R2, R3, R4, R6)?**
**X4. What does the outcome label `hard_landing` tell you about which requirement failed?**
**X5. At what instant did the controller's belief start to diverge from the truth?**
**X6. How far was the believed landing point from the true landing point, and which point of the vehicle does each refer to?**
**X7. How confident was the controller in its estimate during the descent?**
**X8. What were the vertical and horizontal speeds at touchdown, and where do those numbers come from?**
**X9. At exactly what time did the controller first reject the altimeter?**
**X10. Would the current simulator reproduce this run exactly, and how do you know?**
**X11. How many independent detections of a fault did the controller make, and when?**
**X12. When was the keep-out invariant S2 checked, and did it hold?**
**X13. By how much was the GNSS position wrong while the fault was active?**
**X14. How often did the GNSS provide a measurement, and what did it report between measurements?**
**X15. At about 14 s, was the vehicle on course for the pad, and was the estimator working well?**
**X16. Was this run started from the nominal initial state, and how long could the fault have lasted?**
