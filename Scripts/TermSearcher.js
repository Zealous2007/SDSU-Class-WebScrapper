var MaxDepth = 10
var i = 0
var Terms = []

while (i < MaxDepth) {
    let row_element = document.getElementById("SSR_CSTRMCUR_GRD$0_row_"+i)

    if(row_element == null)
        break
    
    let row_text = row_element.textContent
    row_text = row_text.replace(/\n/g, "")
    Terms[i] = row_text
    i+=1
}
Terms
