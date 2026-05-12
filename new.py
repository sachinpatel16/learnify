a = "i am Sachin "

result=""
word=""

for ch in a:
    if ch!=" ":
        word+=ch
    else:
        result= word + " " + result
        word=""


print(result)